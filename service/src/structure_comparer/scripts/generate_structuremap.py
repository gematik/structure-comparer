"""Helper utility to generate StructureMap packages from a mapping project."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from structure_comparer.fshMappingGenerator.fsh_mapping_main import (
    build_structuremap_package,
)
from structure_comparer.handler.mapping import MappingHandler
from structure_comparer.handler.project import ProjectsHandler


def _default_alias(text: str, fallback: str) -> str:
    cleaned = "".join(ch for ch in (text or "") if ch.isalnum())
    return cleaned or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate StructureMap JSON for a mapping")
    parser.add_argument("--project-key", required=True, help="Project directory name under the projects root")
    parser.add_argument("--mapping-id", required=True, help="Mapping identifier inside the project")
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=os.environ.get("STRUCTURE_COMPARER_PROJECTS_DIR"),
        help="Root directory containing all mapping projects",
    )
    parser.add_argument("--ruleset-name", help="Optional custom name for the StructureMap")
    parser.add_argument("--source-alias", help="Override source alias")
    parser.add_argument("--target-alias", help="Override target alias")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the generated StructureMap package (ZIP archive) to this path",
    )

    args = parser.parse_args()

    if args.projects_dir is None:
        parser.error("--projects-dir must be provided (or set STRUCTURE_COMPARER_PROJECTS_DIR)")

    return args


def main() -> None:
    args = parse_args()
    projects_dir = args.projects_dir.expanduser().resolve()

    project_handler = ProjectsHandler(projects_dir)
    project_handler.load()

    mapping_handler = MappingHandler(project_handler)
    mapping = mapping_handler._MappingHandler__get(args.project_key, args.mapping_id)
    actions = mapping.get_action_info_map()

    source_profile = mapping.sources[0] if mapping.sources else None
    target_profile = mapping.target

    source_alias = args.source_alias or _default_alias(getattr(source_profile, "name", ""), "source")
    target_alias = args.target_alias or _default_alias(getattr(target_profile, "name", ""), "target")

    ruleset_name = args.ruleset_name or _default_alias(mapping.name.replace(" ", "_"), "structuremap")

    package = build_structuremap_package(
        mapping=mapping,
        actions=actions,
        source_alias=source_alias,
        target_alias=target_alias,
        ruleset_name=ruleset_name,
    )

    if args.output:
        manifest = package.manifest(
            mapping_id=mapping.id,
            project_key=args.project_key,
            ruleset_name=ruleset_name,
            package_root=".",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(args.output, mode="w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for artifact in package.artifacts:
                zf.writestr(artifact.filename, artifact.content)
        print(f"StructureMap package written to {args.output}")
        return

    if len(package.artifacts) == 1:
        print(package.artifacts[0].content)
        return

    print("Multiple StructureMaps were generated; please rerun with --output <zip_path> to receive the package.")
    sys.exit(1)

if __name__ == "__main__":
    main()
