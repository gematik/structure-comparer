# Structure Comparer — AI Orientation

This document gives an AI the minimal mental model needed to navigate the repository and assist with changes.

## What the system does
- Provides a backend (FastAPI) for creating, inspecting, and exporting mappings between FHIR profiles. The paired frontend lets users author mappings via UI.
- Works on “projects” stored on disk; each project bundles FHIR packages (snapshots), comparison definitions, mapping definitions, transformations (bundle-level mappings), target creations (populate target without sources), and manual overrides.
- Exports mappings as HTML reports and as FHIR StructureMap JSON/FSH artifacts suitable for HAPI/FHIR engines.
- Also offers a CLI to generate outputs or run the service.

## Runtime entry points
- HTTP API: `python -m structure_comparer serve` (or `STRUCTURE_COMPARER_PROJECTS_DIR=../structure-comparer-projects python -m structure_comparer serve`). FastAPI app and routes live in [service/src/structure_comparer/serve.py](service/src/structure_comparer/serve.py).
- CLI: `python -m structure_comparer output --project-dir <proj> --format html|json [--mapping_id <id>]` (see [service/src/main.py](service/src/main.py) and [service/src/structure_comparer/__main__.py](service/src/structure_comparer/__main__.py)).
- Docker: `docker compose up` from `service/` (see [service/README.md](service/README.md)).

## Core data model (project-level)
Each project lives under `STRUCTURE_COMPARER_PROJECTS_DIR/<project-key>/` with a `config.json` describing:
- `packages`: FHIR package references; downloaded packages reside in `<data_dir>/<name>#<version>/package/`.
- `comparisons`: pair source/target profiles to drive automatic comparison.
- `mappings`: field-level mapping definitions for a source→target profile pair.
- `transformations`: bundle-level compositions of mappings.
- `target_creations`: populate a target profile without source data (fixed/manual only).
- `manual_entries_file`: YAML/JSON with human decisions and overrides.
- Output locations: `html_output_dir`, `mapping_output_file`.
See [service/src/structure_comparer/data/config.py](service/src/structure_comparer/data/config.py) and loader in [service/src/structure_comparer/data/project.py](service/src/structure_comparer/data/project.py).

## Key processes
- **Project loading:** [ProjectsHandler](service/src/structure_comparer/handler/project.py) scans the projects dir, loads `config.json`, auto-adopts orphaned packages, and instantiates mappings/comparisons/transformations/target creations.
- **Manual entries:** [manual_entries.py](service/src/structure_comparer/manual_entries.py) reads/writes manual overrides (YAML/JSON), migrates legacy formats, and filters auto-generated helper entries before saving.
- **Mapping management:** [handler/mapping.py](service/src/structure_comparer/handler/mapping.py) exposes CRUD for mappings, fields, and HTML exports; validates actions, partners, and fixed values.
- **StructureMap export:** [fshMappingGenerator/fsh_mapping_main.py](service/src/structure_comparer/fshMappingGenerator/fsh_mapping_main.py) converts mapping/transformations to StructureMap JSON, FSH, and downloadable packages (router + per-source maps, manifest, filenames/URLs).
- **Serving:** [serve.py](service/src/structure_comparer/serve.py) wires FastAPI routes for projects, packages, comparisons, mappings, transformations, target creations, StructureMap downloads, manual entry persistence, and evaluation summaries. CORS allows localhost:4200 (frontend).
- **HTML reporting:** [results_html.py](service/src/structure_comparer/results_html.py) renders mapping comparison results with warnings/remarks toggles.

## Typical workflow
1. Place/prepare a project under `STRUCTURE_COMPARER_PROJECTS_DIR`; ensure `config.json` lists packages and mappings; snapshots must exist in `data/` subfolders.
2. Start backend (`serve`) and use the frontend to load a project.
3. Upload/download FHIR packages via API; server updates `config.json` and caches package state.
4. Create comparisons and mappings; the engine builds field trees from snapshots and proposes allowed actions.
5. Users assign actions (copy value/node, fixed values, manual, etc.); manual entries persist to `manual_entries.yaml`.
6. Optionally define transformations (bundle-level) or target creations (no source data).
7. Export: generate HTML reports or StructureMap JSON/FSH packages for downstream engines (HAPI or other FHIR mappers).

## Repository layout (high level)
- Root: docs/readmes; service code under `service/`; example mapping projects under `structure-comparer-projects/`.
- [service/src/structure_comparer/](service/src/structure_comparer/): domain models, handlers, engines (comparison, mapping, inheritance, recommendations), manual entry handling, StructureMap generator, utilities.
- [service/src/structure_comparer/handler/](service/src/structure_comparer/handler/): route-facing logic for projects, packages, comparisons, mappings, transformations, target creations, dependencies.
- [service/src/structure_comparer/model/](service/src/structure_comparer/model/): Pydantic schemas for API I/O.
- [service/src/structure_comparer/data/](service/src/structure_comparer/data/): in-memory representations of projects, packages, profiles, mappings, comparisons, transformations, target creations.
- [service/docs/](service/docs/): generated HTML mapping reports and supporting CSS.
- [structure-comparer-projects/](structure-comparer-projects/): sample project data and configs for manual testing.

## Behaviors and constraints worth knowing
- Environment variable `STRUCTURE_COMPARER_PROJECTS_DIR` must point to the directory containing projects (default relative path in docs).
- Packages must contain snapshots; missing snapshots raise errors on upload.
- Manual entry persistence strips auto-generated helper fields to keep files clean.
- Actions are validated per field; copy actions require a partner field; fixed actions require a value.
- StructureMap export generates deterministic filenames/IDs and a manifest for package downloads.

## How to ask this AI for help
When asking this AI to change code, mention the relevant layer:
- API surface (FastAPI routes in `serve.py`)
- Handler logic (`handler/*`)
- Domain/data representations (`data/*`)
- Export/generation (StructureMap, HTML, CLI)
- Project config/migrations (config/manual entries)
And specify the target project folder if an operation touches on-disk project data.
