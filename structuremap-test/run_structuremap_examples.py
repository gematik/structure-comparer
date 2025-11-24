#!/usr/bin/env python3
"""Validate StructureMaps and run the HAPI validator using server-generated maps."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from urllib.request import urlopen
from zipfile import ZipFile

# ---------------------------------------------------------------------------
# Edit the values in this block to control what the script processes.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = REPO_ROOT / "structure-comparer-projects"
STRUCTUREMAP_ROOT = Path(__file__).resolve().parent
JAVA_VALIDATOR_JAR = Path("/Users/gematik/dev/validators/current_hapi_validator.jar")
FHIR_VERSION = "4.0.1"
VALIDATE_STRUCTUREMAPS = True
RUN_TRANSFORMATIONS = True  # Enable to run example transformations via validator -transform
PROJECT_FILTER: list[str] = ["dgMP Mapping_2025-10"]  # Leave empty to process every project that exists in the projects dir.
MAPPING_FILTER: list[str] = []  # Optional list of mapping UUIDs to limit the run.
EXAMPLE_FILTER: list[str] = []  # Optional list of resource-type suffixes from example_source_*.json.
EXTRA_IG_SOURCES: list[str | Path] = []  # Additional -ig arguments besides the mapping test folder itself.
ADDITIONAL_TRANSFORM_ARGS: list[str] = []
SERVER_BASE_URL = os.environ.get("STRUCTUREMAP_SERVER_URL", "http://127.0.0.1:8000")
# ---------------------------------------------------------------------------

SERVICE_SRC = REPO_ROOT / "service" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from structure_comparer.handler.mapping import MappingHandler  # type: ignore[import]
from structure_comparer.handler.project import ProjectsHandler  # type: ignore[import]

_STEP_COLOR = "\033[95m"
_RESET_COLOR = "\033[0m"


def _print_step(message: str) -> None:
    print(f"{_STEP_COLOR}{message}{_RESET_COLOR}")


def main() -> None:
    projects_handler = ProjectsHandler(PROJECTS_DIR)
    projects_handler.load()
    mapping_handler = MappingHandler(projects_handler)

    project_keys = PROJECT_FILTER or _discover_projects()
    for project_key in project_keys:
        mapping_dir_root = STRUCTUREMAP_ROOT / project_key
        if not mapping_dir_root.is_dir():
            print(f"Skipping project '{project_key}': structuremap folder {mapping_dir_root} not found")
            continue
        structure_maps_for_validation: list[Path] = []
        transform_jobs: list[tuple[Path, str, str, Path | None]] = []

        for mapping_dir in sorted(p for p in mapping_dir_root.iterdir() if p.is_dir()):
            mapping_id = mapping_dir.name
            if MAPPING_FILTER and mapping_id not in MAPPING_FILTER:
                continue

            downloaded_path = mapping_dir / "downloaded_structuremap.json"
            download_info = _download_structuremap(project_key, mapping_id, downloaded_path)

            mapping_json_path = mapping_dir / "mapping.json"
            _download_mapping(project_key, mapping_id, mapping_json_path)

            if download_info is None:
                structure_map_paths = _find_structuremap_files(mapping_dir)
                if not structure_map_paths:
                    print(f"[{project_key}/{mapping_id}] No StructureMap *.json file found; skipping")
                    continue
                router_map_path = structure_map_paths[0]
                router_map = json.loads(router_map_path.read_text(encoding="utf-8"))
                router_map_url = router_map.get("url", "")
            else:
                structure_map_paths = download_info.files
                router_map_path = download_info.router_path
                router_map_url = download_info.router_url or _read_structuremap_url(router_map_path)
            structure_maps_for_validation.extend(path.resolve() for path in structure_map_paths)

            target_profile = _get_target_profile(mapping_handler, project_key, mapping_id)

            if RUN_TRANSFORMATIONS:
                transform_jobs.append(
                    (
                        mapping_dir,
                        router_map_url,
                        mapping_id,
                        _profile_package_dir(target_profile),
                    )
                )

        validation_ok = _validate_structuremaps(structure_maps_for_validation, project_key)

        if RUN_TRANSFORMATIONS and validation_ok:
            _print_step(f"[{project_key}] Running StructureMap transformations")
            for mapping_dir, structure_map_url, mapping_id, target_package_dir in transform_jobs:
                _run_transformations(
                    mapping_dir=mapping_dir,
                    structure_map_url=structure_map_url,
                    project_key=project_key,
                    mapping_id=mapping_id,
                    target_package_dir=target_package_dir,
                )


def _run_transformations(
    *,
    mapping_dir: Path,
    structure_map_url: str,
    project_key: str,
    mapping_id: str,
    target_package_dir: Path | None,
) -> None:
    if not structure_map_url:
        print(f"[{project_key}/{mapping_id}] Missing StructureMap url, skipping validator")
        return

    if not JAVA_VALIDATOR_JAR.exists():
        print(f"[{project_key}/{mapping_id}] Validator jar not found at {JAVA_VALIDATOR_JAR}")
        return

    example_files = sorted(mapping_dir.glob("example_source_*.json"))
    if not example_files:
        print(f"[{project_key}/{mapping_id}] No example_source_*.json files found")
        return

    mapping_dir_rel = _as_repo_relative(mapping_dir)
    ig_args = ["-ig", mapping_dir_rel]
    for ig in _project_ig_sources(project_key):
        ig_args.extend(["-ig", ig])
    for ig in EXTRA_IG_SOURCES:
        ig_args.extend(["-ig", str(ig)])

    for example_file in example_files:
        resource_type = example_file.stem.split("example_source_", 1)[-1]
        if EXAMPLE_FILTER and resource_type not in EXAMPLE_FILTER:
            continue

        output_file = mapping_dir / f"output-{resource_type}.json"
        if output_file.exists():
            output_file.unlink()
        cmd = [
            "java",
            "-jar",
            str(JAVA_VALIDATOR_JAR),
            _as_repo_relative(example_file),
            "-transform",
            structure_map_url,
            "-version",
            FHIR_VERSION,
            "-output",
            _as_repo_relative(output_file),
        ]
        cmd.extend(ig_args)
        cmd.extend(ADDITIONAL_TRANSFORM_ARGS)

        _print_step(f"[{project_key}/{mapping_id}] Transforming {example_file.name} via StructureMap")
        try:
            subprocess.run(cmd, cwd=REPO_ROOT, check=True)
        except subprocess.CalledProcessError as exc:  # noqa: PERF203 - want explicit feedback
            print(f"[{project_key}/{mapping_id}] Validator failed for {example_file.name}: {exc}")
        else:
            if output_file.exists() and output_file.stat().st_size > 0:
                _print_step(f"[{project_key}/{mapping_id}] Output written to {_as_repo_relative(output_file)}")
                _validate_transformed_output(
                    output_file=output_file,
                    project_key=project_key,
                    mapping_id=mapping_id,
                    resource_type=resource_type,
                    target_package_dir=target_package_dir,
                )
            else:
                print(
                    f"[{project_key}/{mapping_id}] Validator finished but no output file was produced for {example_file.name}."
                )


def _profile_package_dir(profile) -> Path | None:
    package_dir = getattr(profile, "package_dir", None)
    if not package_dir:
        return None
    return Path(package_dir)


def _validate_structuremaps(structure_map_paths: list[Path], project_key: str) -> bool:
    if not VALIDATE_STRUCTUREMAPS or not structure_map_paths:
        return True

    if not JAVA_VALIDATOR_JAR.exists():
        print(f"[{project_key}] Validator jar not found at {JAVA_VALIDATOR_JAR}, skipping StructureMap validation")
        return False

    cmd = [
        "java",
        "-jar",
        str(JAVA_VALIDATOR_JAR),
        "-tx",
        "n/a",
        "-level",
        "error",
    ]
    ig_args = ["hl7.fhir.r4.core#4.0.1", *_project_ig_sources(project_key)]
    ig_args.extend(str(ig) for ig in EXTRA_IG_SOURCES)
    for ig in ig_args:
        cmd.extend(["-ig", ig])
    cmd.extend(str(path) for path in structure_map_paths)

    _print_step(f"[{project_key}] Validating {len(structure_map_paths)} StructureMap(s)")
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:  # noqa: PERF203 - want explicit feedback
        print(f"[{project_key}] StructureMap validation failed: {exc}")
        return False
    else:
        _print_step(f"[{project_key}] StructureMap validation finished successfully")
        return True


def _project_ig_sources(project_key: str) -> list[str]:
    data_dir = PROJECTS_DIR / project_key / "data"
    igs: list[str] = []
    if not data_dir.is_dir():
        return igs

    for entry in sorted(data_dir.iterdir()):
        if entry.is_file() and entry.suffix == ".tgz":
            igs.append(_as_repo_relative(entry))
            continue

        if not entry.is_dir():
            continue

        package_dir = entry / "package"
        target_dir = package_dir if package_dir.is_dir() else entry
        if (target_dir / "package.json").exists():
            igs.append(_as_repo_relative(target_dir))

    return igs


def _validate_transformed_output(
    *,
    output_file: Path,
    project_key: str,
    mapping_id: str,
    resource_type: str,
    target_package_dir: Path | None,
) -> None:
    if target_package_dir is None:
        print(
            f"[{project_key}/{mapping_id}] Target package not available; skipping validation for output-{resource_type}.json"
        )
        return

    if not target_package_dir.exists():
        print(
            f"[{project_key}/{mapping_id}] Target package path {target_package_dir} does not exist; skipping validation"
        )
        return

    cmd = [
        "java",
        "-jar",
        str(JAVA_VALIDATOR_JAR),
        _as_repo_relative(output_file),
        "-tx",
        "n/a",
        "-level",
        "error",
        "-version",
        FHIR_VERSION,
        "-ig",
        _as_repo_relative(target_package_dir),
    ]

    _print_step(
        f"[{project_key}/{mapping_id}] Validating output-{resource_type}.json against {_as_repo_relative(target_package_dir)}"
    )
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:  # noqa: PERF203 - want explicit feedback
        print(f"[{project_key}/{mapping_id}] Output validation failed for output-{resource_type}.json: {exc}")


@dataclass
class DownloadedStructureMap:
    files: list[Path]
    router_path: Path
    router_url: str | None


def _download_structuremap(project_key: str, mapping_id: str, destination: Path) -> DownloadedStructureMap | None:
    encoded_project = quote(project_key, safe="")
    encoded_mapping = quote(mapping_id, safe="")
    url = f"{SERVER_BASE_URL}/project/{encoded_project}/mapping/{encoded_mapping}/structuremap"
    _print_step(f"[{project_key}/{mapping_id}] Downloading StructureMap from {url}")
    try:
        with urlopen(url) as response:
            content_bytes = response.read()
            content_type = response.info().get_content_type()
    except HTTPError as exc:
        print(f"[{project_key}/{mapping_id}] Failed to download StructureMap: HTTP {exc.code} {exc.reason}")
        return None
    except URLError as exc:
        print(f"[{project_key}/{mapping_id}] Failed to reach StructureMap endpoint: {exc}")
        return None

    if _is_zip_payload(content_bytes, content_type):
        return _process_structuremap_zip(content_bytes, destination)

    content = content_bytes.decode("utf-8")
    destination.write_text(content, encoding="utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"[{project_key}/{mapping_id}] Downloaded StructureMap is not valid JSON: {exc}")
        return None
    return DownloadedStructureMap(files=[destination], router_path=destination, router_url=data.get("url"))


def _is_zip_payload(content: bytes, content_type: str | None) -> bool:
    if content_type and content_type.lower() == "application/zip":
        return True
    return content.startswith(b"PK")


def _process_structuremap_zip(content_bytes: bytes, destination: Path) -> DownloadedStructureMap | None:
    zip_path = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(content_bytes)

    with ZipFile(zip_path) as zf:
        manifest_name = next((name for name in zf.namelist() if name.endswith("manifest.json")), None)
        if manifest_name is None:
            print("[structuremap] ZIP package missing manifest.json; skipping")
            return None
        manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
        package_root = manifest.get("packageRoot") or Path(manifest_name).parent.as_posix()
        extract_root = destination.parent / package_root
        if extract_root.exists():
            shutil.rmtree(extract_root)
        zf.extractall(destination.parent)

    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        print("[structuremap] ZIP package contains no artifacts; skipping")
        return None

    artifact_files: list[Path] = []
    for artifact in artifacts:
        filename = artifact.get("filename")
        if not filename:
            continue
        artifact_files.append((extract_root / filename).resolve())

    if not artifact_files:
        print("[structuremap] No artifact files extracted; skipping")
        return None

    router_entry = next((a for a in artifacts if a.get("kind") == "router"), artifacts[0])
    router_filename = router_entry.get("filename") or artifacts[0].get("filename")
    router_path = (extract_root / router_filename).resolve()
    if router_path.exists():
        destination.write_text(router_path.read_text(encoding="utf-8"), encoding="utf-8")

    return DownloadedStructureMap(
        files=artifact_files,
        router_path=router_path,
        router_url=router_entry.get("structureMapUrl"),
    )


def _download_mapping(project_key: str, mapping_id: str, destination: Path) -> None:
    encoded_project = quote(project_key, safe="")
    encoded_mapping = quote(mapping_id, safe="")
    url = f"{SERVER_BASE_URL}/project/{encoded_project}/mapping/{encoded_mapping}"
    _print_step(f"[{project_key}/{mapping_id}] Downloading Mapping from {url}")
    try:
        with urlopen(url) as response:
            content_bytes = response.read()
    except HTTPError as exc:
        print(f"[{project_key}/{mapping_id}] Failed to download Mapping: HTTP {exc.code} {exc.reason}")
        return
    except URLError as exc:
        print(f"[{project_key}/{mapping_id}] Failed to reach Mapping endpoint: {exc}")
        return

    content = content_bytes.decode("utf-8")
    destination.write_text(content, encoding="utf-8")


def _find_structuremap_files(mapping_dir: Path) -> list[Path]:
    candidates = sorted(
        p for p in mapping_dir.glob("**/*.json") if "structuremap" in p.stem.lower() and not p.name.startswith("output")
    )
    return candidates


def _read_structuremap_url(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return data.get("url", "")


def _discover_projects() -> list[str]:
    return sorted(p.name for p in STRUCTUREMAP_ROOT.iterdir() if p.is_dir())


def _get_target_profile(mapping_handler: MappingHandler, project_key: str, mapping_id: str):
    try:
        mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
    except Exception:
        return None
    return mapping.target

def _as_repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
