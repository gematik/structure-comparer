#!/usr/bin/env python3
"""Validate StructureMaps and run the HAPI validator using server-generated maps."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
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
TRANSFORMATION_FILTER: list[str] = []  # Optional list of transformation UUIDs to limit the run.
EXAMPLE_FILTER: list[str] = []  # Optional list of example descriptor suffixes (text after the UUID in the filename).
EXTRA_IG_SOURCES: list[str | Path] = []  # Additional -ig arguments besides the mapping test folder itself.
ADDITIONAL_TRANSFORM_ARGS: list[str] = []
SERVER_BASE_URL = os.environ.get("STRUCTUREMAP_SERVER_URL", "http://127.0.0.1:8000")
# ---------------------------------------------------------------------------

SERVICE_SRC = REPO_ROOT / "service" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from structure_comparer.handler.mapping import MappingHandler  # type: ignore[import]
from structure_comparer.handler.project import ProjectsHandler  # type: ignore[import]
from structure_comparer.handler.transformation import TransformationHandler  # type: ignore[import]

_STEP_COLOR = "\033[95m"
_RESET_COLOR = "\033[0m"


def _print_step(message: str) -> None:
    print(f"{_STEP_COLOR}{message}{_RESET_COLOR}")


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    structuremaps: Path
    input_examples: Path
    outputs: Path


@dataclass(frozen=True)
class StructureMapArtifacts:
    identifier: str
    kind: str
    directory: Path
    router_path: Path
    router_url: str | None
    files: list[Path]


@dataclass(frozen=True)
class TransformJob:
    project_key: str
    identifier: str
    kind: str
    structuremap_dir: Path
    structure_map_url: str
    target_package_dir: Path | None
    example_files: list[Path]
    output_dir: Path
    dependency_dirs: tuple[Path, ...] = tuple()


@dataclass
class DownloadedStructureMap:
    files: list[Path]
    router_path: Path
    router_url: str | None

    def rebase(self, old_root: Path, new_root: Path) -> "DownloadedStructureMap":
        def _rebase_path(path: Path) -> Path:
            rel = path.relative_to(old_root)
            return (new_root / rel).resolve()

        return DownloadedStructureMap(
            files=[_rebase_path(path) for path in self.files],
            router_path=_rebase_path(self.router_path),
            router_url=self.router_url,
        )


def main() -> None:
    projects_handler = ProjectsHandler(PROJECTS_DIR)
    projects_handler.load()
    mapping_handler = MappingHandler(projects_handler)
    transformation_handler = TransformationHandler(projects_handler)

    project_keys = PROJECT_FILTER or _discover_projects()
    for project_key in project_keys:
        project_dir = STRUCTUREMAP_ROOT / project_key
        if not project_dir.is_dir():
            print(f"Skipping project '{project_key}': structuremap folder {project_dir} not found")
            continue

        try:
            project = mapping_handler.project_handler._get(project_key)
        except Exception as exc:  # noqa: BLE001 - surface configuration issues
            print(f"[{project_key}] Failed to load project data: {exc}")
            continue

        project.load_mappings()
        project.load_transformations()
        mapping_objects = project.mappings or {}
        transformation_objects = getattr(project, "transformations", {}) or {}
        known_identifiers = set(mapping_objects.keys()) | set(transformation_objects.keys())

        paths = _ensure_project_paths(project_dir)
        example_index = _index_examples(paths.input_examples, known_identifiers)

        structure_map_paths: set[Path] = set()
        transform_jobs: list[TransformJob] = []
        mapping_artifacts: dict[str, StructureMapArtifacts] = {}

        for mapping_id in sorted(mapping_objects.keys()):
            artifacts = _prepare_mapping_artifacts(
                project_key=project_key,
                mapping_id=mapping_id,
                structuremaps_dir=paths.structuremaps,
            )
            if artifacts is None:
                continue
            mapping_artifacts[mapping_id] = artifacts
            structure_map_paths.update(path.resolve() for path in artifacts.files)

            if MAPPING_FILTER and mapping_id not in MAPPING_FILTER:
                continue

            router_url = artifacts.router_url or _read_structuremap_url(artifacts.router_path)
            target_profile = mapping_objects[mapping_id].target if mapping_objects.get(mapping_id) else None
            transform_jobs.append(
                TransformJob(
                    project_key=project_key,
                    identifier=mapping_id,
                    kind="mapping",
                    structuremap_dir=artifacts.directory,
                    structure_map_url=router_url,
                    target_package_dir=_profile_package_dir(target_profile),
                    example_files=example_index.get(mapping_id, []),
                    output_dir=paths.outputs,
                )
            )

        for transformation_id, transformation in sorted(transformation_objects.items()):
            artifacts = _prepare_transformation_artifacts(
                project_key=project_key,
                transformation_id=transformation_id,
                structuremaps_dir=paths.structuremaps,
            )
            if artifacts is None:
                continue
            structure_map_paths.update(path.resolve() for path in artifacts.files)

            if TRANSFORMATION_FILTER and transformation_id not in TRANSFORMATION_FILTER:
                continue

            router_url = artifacts.router_url or _read_structuremap_url(artifacts.router_path)
            dependency_dirs = _transformation_dependency_directories(
                project_key=project_key,
                transformation_id=transformation_id,
                transformation=transformation,
                mapping_artifacts=mapping_artifacts,
            )
            transform_jobs.append(
                TransformJob(
                    project_key=project_key,
                    identifier=transformation_id,
                    kind="transformation",
                    structuremap_dir=artifacts.directory,
                    structure_map_url=router_url,
                    target_package_dir=_profile_package_dir(getattr(transformation, "target", None)),
                    example_files=example_index.get(transformation_id, []),
                    output_dir=paths.outputs,
                    dependency_dirs=dependency_dirs,
                )
            )

        validation_ok = _validate_structuremaps(sorted(structure_map_paths), project_key)

        if RUN_TRANSFORMATIONS:
            if not validation_ok:
                print(
                    f"[{project_key}] Continuing with transformations despite validation errors; see validator output above"
                )
            _print_step(f"[{project_key}] Running StructureMap transformations")
            for job in transform_jobs:
                _run_transform_job(job)


def _run_transform_job(job: TransformJob) -> None:
    if not job.structure_map_url:
        print(f"[{job.project_key}/{job.identifier}] Missing StructureMap url, skipping validator")
        return

    if not JAVA_VALIDATOR_JAR.exists():
        print(f"[{job.project_key}/{job.identifier}] Validator jar not found at {JAVA_VALIDATOR_JAR}")
        return

    example_files = job.example_files or []
    if not example_files:
        print(f"[{job.project_key}/{job.identifier}] No example input files found")
        return

    base_ig_args: list[str] = ["-ig", _as_repo_relative(job.structuremap_dir)]
    for dep_dir in job.dependency_dirs:
        base_ig_args.extend(["-ig", _as_repo_relative(dep_dir)])
    for ig in _project_ig_sources(job.project_key):
        base_ig_args.extend(["-ig", ig])
    for ig in EXTRA_IG_SOURCES:
        base_ig_args.extend(["-ig", str(ig)])

    job.output_dir.mkdir(parents=True, exist_ok=True)

    for example_file in example_files:
        descriptor = _example_descriptor(example_file)
        if EXAMPLE_FILTER and descriptor not in EXAMPLE_FILTER:
            continue

        output_name = f"output_{job.identifier}_{descriptor}.json"
        output_file = job.output_dir / output_name
        if output_file.exists():
            output_file.unlink()

        cmd = [
            "java",
            "-jar",
            str(JAVA_VALIDATOR_JAR),
            _as_repo_relative(example_file),
            "-transform",
            job.structure_map_url,
            "-version",
            FHIR_VERSION,
            "-output",
            _as_repo_relative(output_file),
        ]
        cmd.extend(base_ig_args)
        cmd.extend(ADDITIONAL_TRANSFORM_ARGS)

        _print_step(f"[{job.project_key}/{job.identifier}] Transforming {example_file.name} via StructureMap")
        try:
            subprocess.run(cmd, cwd=REPO_ROOT, check=True)
        except subprocess.CalledProcessError as exc:  # noqa: PERF203 - want explicit feedback
            print(f"[{job.project_key}/{job.identifier}] Validator failed for {example_file.name}: {exc}")
            continue

        if output_file.exists() and output_file.stat().st_size > 0:
            _print_step(f"[{job.project_key}/{job.identifier}] Output written to {_as_repo_relative(output_file)}")
            _validate_transformed_output(
                output_file=output_file,
                project_key=job.project_key,
                identifier=job.identifier,
                resource_type=descriptor,
                target_package_dir=job.target_package_dir,
            )
        else:
            print(
                f"[{job.project_key}/{job.identifier}] Validator finished but no output file was produced for {example_file.name}."
            )


def _ensure_project_paths(project_dir: Path) -> ProjectPaths:
    structuremaps = project_dir / "structuremaps"
    input_examples = project_dir / "input_examples"
    outputs = project_dir / "outputs"
    for path in (structuremaps, input_examples, outputs):
        path.mkdir(parents=True, exist_ok=True)
    return ProjectPaths(
        project_root=project_dir,
        structuremaps=structuremaps,
        input_examples=input_examples,
        outputs=outputs,
    )


def _prepare_mapping_artifacts(
    *,
    project_key: str,
    mapping_id: str,
    structuremaps_dir: Path,
) -> StructureMapArtifacts | None:
    target_dir = structuremaps_dir / mapping_id
    download_info = _download_structuremap(
        project_key=project_key,
        identifier=mapping_id,
        target_dir=target_dir,
        expected_kind="mapping",
    )
    if download_info is None:
        print(f"[{project_key}/{mapping_id}] Unable to download StructureMap; skipping")
        return None

    mapping_json_path = target_dir / "mapping.json"
    _download_mapping(project_key, mapping_id, mapping_json_path)

    return StructureMapArtifacts(
        identifier=mapping_id,
        kind="mapping",
        directory=target_dir,
        router_path=download_info.router_path,
        router_url=download_info.router_url,
        files=[path.resolve() for path in download_info.files],
    )


def _prepare_transformation_artifacts(
    *,
    project_key: str,
    transformation_id: str,
    structuremaps_dir: Path,
) -> StructureMapArtifacts | None:
    target_dir = structuremaps_dir / transformation_id
    download_info = _download_transformation_structuremap(
        project_key=project_key,
        transformation_id=transformation_id,
        target_dir=target_dir,
    )
    if download_info is None:
        print(f"[{project_key}/{transformation_id}] Unable to download transformation StructureMap; skipping")
        return None

    transformation_json_path = target_dir / "transformation.json"
    _download_transformation_details(project_key, transformation_id, transformation_json_path)

    return StructureMapArtifacts(
        identifier=transformation_id,
        kind="transformation",
        directory=target_dir,
        router_path=download_info.router_path,
        router_url=download_info.router_url,
        files=[path.resolve() for path in download_info.files],
    )


def _index_examples(examples_dir: Path, known_identifiers: set[str]) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    if not examples_dir.exists():
        return index

    for example_path in sorted(examples_dir.glob("example_*.json"), key=lambda p: p.name):
        identifier, _descriptor = _parse_example_filename(example_path)
        if identifier is None:
            print(f"[examples] Skipping {example_path.name}: unable to determine identifier from filename")
            continue
        if known_identifiers and identifier not in known_identifiers:
            print(f"[examples] {example_path.name} references unknown id {identifier}; skipping")
            continue
        index.setdefault(identifier, []).append(example_path)
    return index


def _parse_example_filename(path: Path) -> tuple[str | None, str]:
    stem = path.stem
    if not stem.startswith("example_"):
        return None, stem
    remainder = stem[len("example_") :]
    if not remainder:
        return None, "payload"
    if "_" in remainder:
        identifier, descriptor = remainder.split("_", 1)
        descriptor = descriptor or "payload"
        return identifier, descriptor
    return remainder, "payload"


def _example_descriptor(path: Path) -> str:
    _identifier, descriptor = _parse_example_filename(path)
    return descriptor or "payload"


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
    sources = _project_ig_entries(project_key)
    return [_as_repo_relative(src.path) for src in sources if src.path]


def _project_ig_package_specs(project_key: str) -> list[str]:
    sources = _project_ig_entries(project_key)
    specs: list[str] = []
    for src in sources:
        if src.package_spec:
            specs.append(src.package_spec)
        elif src.path:
            specs.append(_as_repo_relative(src.path))
    return specs


@dataclass(frozen=True)
class ProjectIGSource:
    package_spec: str | None
    path: Path | None


def _project_ig_entries(project_key: str) -> list[ProjectIGSource]:
    data_dir = PROJECTS_DIR / project_key / "data"
    sources: list[ProjectIGSource] = []
    if not data_dir.is_dir():
        return sources

    for entry in sorted(data_dir.iterdir()):
        if entry.is_file() and entry.suffix == ".tgz":
            sources.append(ProjectIGSource(_package_spec_from_name(entry.name), entry))
            continue

        if not entry.is_dir():
            continue

        package_dir = entry / "package"
        target_dir = package_dir if package_dir.is_dir() else entry
        if (target_dir / "package.json").exists():
            sources.append(ProjectIGSource(_package_spec_from_name(entry.name), target_dir))

    return sources


def _package_spec_from_name(name: str) -> str | None:
    cleaned = name
    if cleaned.endswith(".tar.gz"):
        cleaned = cleaned[: -len(".tar.gz")]
    elif cleaned.endswith(".tgz"):
        cleaned = cleaned[: -len(".tgz")]
    elif cleaned.endswith(".tar"):
        cleaned = cleaned[: -len(".tar")]
    elif cleaned.endswith(".zip"):
        cleaned = cleaned[: -len(".zip")]

    return cleaned if "#" in cleaned else None


def _validate_transformed_output(
    *,
    output_file: Path,
    project_key: str,
    identifier: str,
    resource_type: str,
    target_package_dir: Path | None,
) -> None:
    if target_package_dir is None:
        print(
            f"[{project_key}/{identifier}] Target package not available; skipping validation for output-{resource_type}.json"
        )
        return

    if not target_package_dir.exists():
        print(
            f"[{project_key}/{identifier}] Target package path {target_package_dir} does not exist; skipping validation"
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
    ]
    ig_args = [_as_repo_relative(target_package_dir)]
    ig_args.extend(_project_ig_package_specs(project_key))
    ig_args.extend(str(ig) for ig in EXTRA_IG_SOURCES)

    seen_igs: set[str] = set()
    for ig in ig_args:
        if not ig or ig in seen_igs:
            continue
        seen_igs.add(ig)
        cmd.extend(["-ig", ig])

    _print_step(
        f"[{project_key}/{identifier}] Validating {output_file.name} against "
        f"{_as_repo_relative(target_package_dir)} + project IGs"
    )
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:  # noqa: PERF203 - want explicit feedback
        print(f"[{project_key}/{identifier}] Output validation failed for output-{resource_type}.json: {exc}")


def _download_structuremap(
    *,
    project_key: str,
    identifier: str,
    target_dir: Path,
    expected_kind: str,
) -> DownloadedStructureMap | None:
    encoded_project = quote(project_key, safe="")
    encoded_identifier = quote(identifier, safe="")
    if expected_kind == "mapping":
        url = f"{SERVER_BASE_URL}/project/{encoded_project}/mapping/{encoded_identifier}/structuremap"
    else:
        url = f"{SERVER_BASE_URL}/project/{encoded_project}/transformation/{encoded_identifier}/structuremap"
    return _download_structuremap_from_url(url, f"{project_key}/{identifier}", target_dir)


def _download_transformation_structuremap(
    *,
    project_key: str,
    transformation_id: str,
    target_dir: Path,
) -> DownloadedStructureMap | None:
    return _download_structuremap(
        project_key=project_key,
        identifier=transformation_id,
        target_dir=target_dir,
        expected_kind="transformation",
    )


def _download_structuremap_from_url(url: str, log_label: str, target_dir: Path) -> DownloadedStructureMap | None:
    _print_step(f"[{log_label}] Downloading StructureMap from {url}")
    try:
        with urlopen(url) as response:
            content_bytes = response.read()
            content_type = response.info().get_content_type()
    except HTTPError as exc:
        print(f"[{log_label}] Failed to download StructureMap: HTTP {exc.code} {exc.reason}")
        return None
    except URLError as exc:
        print(f"[{log_label}] Failed to reach StructureMap endpoint: {exc}")
        return None

    target_dir = target_dir.resolve()
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if _is_zip_payload(content_bytes, content_type):
        return _process_structuremap_zip(content_bytes, target_dir)

    return _process_structuremap_json(content_bytes, target_dir, log_label)


def _download_mapping(project_key: str, mapping_id: str, destination: Path) -> None:
    encoded_project = quote(project_key, safe="")
    encoded_mapping = quote(mapping_id, safe="")
    url = f"{SERVER_BASE_URL}/project/{encoded_project}/mapping/{encoded_mapping}"
    _download_json_from_url(url, f"{project_key}/{mapping_id}", "Mapping", destination)


def _download_transformation_details(project_key: str, transformation_id: str, destination: Path) -> None:
    encoded_project = quote(project_key, safe="")
    encoded_transformation = quote(transformation_id, safe="")
    url = f"{SERVER_BASE_URL}/project/{encoded_project}/transformation/{encoded_transformation}"
    _download_json_from_url(url, f"{project_key}/{transformation_id}", "Transformation", destination)


def _download_json_from_url(url: str, log_label: str, entity_name: str, destination: Path) -> None:
    _print_step(f"[{log_label}] Downloading {entity_name} from {url}")
    try:
        with urlopen(url) as response:
            content_bytes = response.read()
    except HTTPError as exc:
        print(f"[{log_label}] Failed to download {entity_name}: HTTP {exc.code} {exc.reason}")
        return
    except URLError as exc:
        print(f"[{log_label}] Failed to reach {entity_name} endpoint: {exc}")
        return

    content = content_bytes.decode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def _is_zip_payload(content: bytes, content_type: str | None) -> bool:
    if content_type and content_type.lower() == "application/zip":
        return True
    return content.startswith(b"PK")


def _process_structuremap_zip(content_bytes: bytes, target_dir: Path) -> DownloadedStructureMap | None:
    with ZipFile(io.BytesIO(content_bytes)) as zf:
        zf.extractall(target_dir)

    manifest_path = _find_manifest(target_dir)
    if manifest_path is None:
        print("[structuremap] ZIP package missing manifest.json; skipping")
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        print("[structuremap] ZIP package contains no artifacts; skipping")
        return None

    package_root = manifest.get("packageRoot") or "."
    artifact_files: list[Path] = []
    for artifact in artifacts:
        filename = artifact.get("filename")
        if not filename:
            continue
        artifact_files.append((target_dir / package_root / filename).resolve())

    artifact_files = [path for path in artifact_files if path.exists()]
    if not artifact_files:
        print("[structuremap] Extracted package contained no readable artifact files; skipping")
        return None

    router_entry = next((a for a in artifacts if a.get("kind") == "router"), artifacts[0])
    router_filename = router_entry.get("filename") or artifacts[0].get("filename")
    router_path = (target_dir / package_root / router_filename).resolve()
    if not router_path.exists():
        router_path = artifact_files[0]

    return DownloadedStructureMap(
        files=artifact_files,
        router_path=router_path,
        router_url=router_entry.get("structureMapUrl"),
    )


def _process_structuremap_json(content_bytes: bytes, target_dir: Path, log_label: str) -> DownloadedStructureMap | None:
    try:
        data = json.loads(content_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[{log_label}] Downloaded StructureMap is not valid JSON: {exc}")
        return None

    filename = _safe_filename(data.get("name") or data.get("id") or "StructureMap")
    router_path = (target_dir / f"{filename}.json").resolve()
    router_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "packageVersion": "local",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "packageRoot": ".",
        "artifacts": [
            {
                "filename": router_path.name,
                "kind": "router",
                "structureMapUrl": data.get("url"),
            }
        ],
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return DownloadedStructureMap(files=[router_path], router_path=router_path, router_url=data.get("url"))


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


def _read_structuremap_url(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return data.get("url", "")


def _discover_projects() -> list[str]:
    return sorted(p.name for p in STRUCTUREMAP_ROOT.iterdir() if p.is_dir())


def _transformation_dependency_directories(
    *,
    project_key: str,
    transformation_id: str,
    transformation,
    mapping_artifacts: dict[str, StructureMapArtifacts],
) -> tuple[Path, ...]:
    if transformation is None:
        return tuple()

    dependency_ids = sorted(getattr(transformation, "linked_mapping_ids", []) or [])
    if not dependency_ids:
        return tuple()

    directories: list[Path] = []
    seen: set[Path] = set()
    for mapping_id in dependency_ids:
        artifacts = mapping_artifacts.get(mapping_id)
        if artifacts is None:
            print(
                f"[{project_key}/{transformation_id}] Mapping dependency '{mapping_id}' was not prepared; "
                "StructureMap import may fail"
            )
            continue
        resolved = artifacts.directory.resolve()
        if resolved not in seen:
            directories.append(resolved)
            seen.add(resolved)
    return tuple(directories)


def _profile_package_dir(profile) -> Path | None:  # type: ignore[override]
    """Return the on-disk package directory for a profile if available."""
    if profile is None:
        return None

    package_dir = getattr(profile, "package_dir", None)
    if isinstance(package_dir, Path):
        return package_dir

    if package_dir is not None:
        return Path(package_dir)

    return None


def _find_manifest(directory: Path) -> Path | None:
    candidate = directory / "manifest.json"
    if candidate.is_file():
        return candidate
    for path in directory.rglob("manifest.json"):
        if path.is_file():
            return path
    return None


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return sanitized or "structuremap"


def _as_repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
