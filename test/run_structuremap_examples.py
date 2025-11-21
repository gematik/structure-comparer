#!/usr/bin/env python3
"""Generate StructureMaps for test fixtures and optionally run the HAPI validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Edit the values in this block to control what the script processes.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = REPO_ROOT / "structure-comparer-projects"
TEST_ROOT = REPO_ROOT / "test"
JAVA_VALIDATOR_JAR = Path("/Users/gematik/dev/validators/current_hapi_validator.jar")
FHIR_VERSION = "4.0.1"
VALIDATE_STRUCTUREMAPS = True
RUN_TRANSFORMATIONS = True  # Enable to run example transformations via validator -transform
PROJECT_FILTER: list[str] = ["dgMP Mapping_2025-10"]  # Leave empty to process every project that exists in the projects dir.
MAPPING_FILTER: list[str] = ["3b4c5d6e-7f81-4b92-a3c4-2d3e4f5a6702"]  # Optional list of mapping UUIDs to limit the run.
EXAMPLE_FILTER: list[str] = []  # Optional list of resource-type suffixes from example_source_*.json.
RULESET_OVERRIDES: dict[str, str] = {
    # "3b4c5d6e-7f81-4b92-a3c4-2d3e4f5a6702": "MedicationRequestMap",
}
SOURCE_ALIAS_OVERRIDES: dict[str, str] = {}
TARGET_ALIAS_OVERRIDES: dict[str, str] = {}
EXTRA_IG_SOURCES: list[str | Path] = []  # Additional -ig arguments besides the mapping test folder itself.
ADDITIONAL_TRANSFORM_ARGS: list[str] = []
# ---------------------------------------------------------------------------

SERVICE_SRC = REPO_ROOT / "service" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from structure_comparer.fshMappingGenerator.fsh_mapping_main import build_structuremap_fsh  # type: ignore[import]
from structure_comparer.handler.mapping import MappingHandler  # type: ignore[import]
from structure_comparer.handler.project import ProjectsHandler  # type: ignore[import]

_STEP_COLOR = "\033[95m"
_RESET_COLOR = "\033[0m"


def _print_step(message: str) -> None:
    print(f"{_STEP_COLOR}{message}{_RESET_COLOR}")


def _default_alias(text: str, fallback: str) -> str:
    cleaned = "".join(ch for ch in (text or "") if ch.isalnum())
    return cleaned or fallback


def main() -> None:
    projects_handler = ProjectsHandler(PROJECTS_DIR)
    projects_handler.load()
    mapping_handler = MappingHandler(projects_handler)

    project_keys = PROJECT_FILTER or projects_handler.keys
    for project_key in project_keys:
        try:
            project = projects_handler._get(project_key)
        except Exception as exc:  # noqa: BLE001 - propagate useful context later
            print(f"Skipping project '{project_key}': {exc}")
            continue

        mapping_dir_root = TEST_ROOT / project_key
        mapping_dir_root.mkdir(parents=True, exist_ok=True)
        structure_maps_for_validation: list[Path] = []
        transform_jobs: list[tuple[Path, str, str, Path | None]] = []

        for mapping_id in project.mappings.keys():
            if MAPPING_FILTER and mapping_id not in MAPPING_FILTER:
                continue

            mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
            actions = mapping.get_action_info_map()

            source_profile = mapping.sources[0] if mapping.sources else None
            target_profile = mapping.target

            source_alias = SOURCE_ALIAS_OVERRIDES.get(mapping_id) or _default_alias(
                getattr(source_profile, "name", ""),
                "source",
            )
            target_alias = TARGET_ALIAS_OVERRIDES.get(mapping_id) or _default_alias(
                getattr(target_profile, "name", ""),
                "target",
            )
            ruleset_name = RULESET_OVERRIDES.get(mapping_id) or _default_alias(
                mapping.name.replace(" ", "_"),
                "structuremap",
            )

            structure_map_json = build_structuremap_fsh(
                mapping=mapping,
                actions=actions,
                source_alias=source_alias,
                target_alias=target_alias,
                ruleset_name=ruleset_name,
            )
            structure_map = json.loads(structure_map_json)

            mapping_dir = mapping_dir_root / mapping_id
            mapping_dir.mkdir(parents=True, exist_ok=True)
            structure_map_path = mapping_dir / f"{ruleset_name}.json"
            structure_map_path.write_text(structure_map_json, encoding="utf-8")
            _print_step(f"[{project_key}/{mapping_id}] StructureMap saved to {_as_repo_relative(structure_map_path)}")
            structure_maps_for_validation.append(structure_map_path.resolve())
            if RUN_TRANSFORMATIONS:
                transform_jobs.append(
                    (
                        mapping_dir,
                        structure_map.get("url", ""),
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

def _as_repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
