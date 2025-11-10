# Structure Comparer Service

The services can serve a backend for the web app or can be me used in CLI mode (WIP).

A directory to store all data for projects is assumed to be at `../structure-comparer-projects`.

## Backend

The server will be available at `localhost:8000`. The OpenAPI specification is available with the route `/docs`.

### Docker

From `service/` build and start the image with

```bash
docker compose up
```

## CLI mode (WIP)
The CLI mode is currently a work in progress. However, the following functionality is already available:

### Generating a file containing a mapping 
(Currently only HTML is supported, but JSON support is coming soon)
```bash
python -m structure_comparer output --project-dir {project directory} --format html --mapping_id {mapping id}
```
Both --format and --mapping_id are optional. 
The default format is HTML. If --mapping_id is omitted, the tool will generate files for all the mappings contained in the project.

### Developers

The project uses _Poetry_ for the project set-up but can also be installed with plain `pip`.

Either way after installing the service can be started with

```bash
export STRUCTURE_COMPARER_PROJECTS_DIR=../structure-comparer-projects

python -m structure_comparer serve
```

The server will be available at `localhost:5000`. The OpenAPI specification is available with the route `/spec`.

#### Poetry

Install all dependencies and the project itself from `service/`

```bash
pip install poetry
poetry install
```

#### pip

Install all dependencies and the project itself from `./service` as an editable dependency

```bash
pip install --editable .
```

### Tests

Run all tests with

```bash
pytest
```
