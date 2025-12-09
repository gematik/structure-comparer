import io
import json
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import uvicorn
import yaml
from fastapi import FastAPI, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

# Configure logging at module level so it works with uvicorn --reload
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s: %(message)s'
)

from .errors import (
    ComparisonNotFound,
    FieldNotFound,
    InvalidFileFormat,
    MappingActionNotAllowed,
    MappingNotFound,
    MappingTargetMissing,
    MappingTargetNotFound,
    MappingValueMissing,
    NotAllowed,
    PackageAlreadyExists,
    PackageCorrupted,
    PackageNoSnapshots,
    PackageNotFound,
    ProjectAlreadyExists,
    ProjectNotFound,
)
from .handler.comparison import ComparisonHandler
from .handler.mapping import MappingHandler
from .handler.transformation import TransformationHandler, TransformationNotFound
from .handler.target_creation import TargetCreationHandler, TargetCreationNotFound
from .handler.package import PackageHandler
from .handler.project import ProjectsHandler
from .model.action import ActionOutput as ActionOutputModel
from .model.comparison import ComparisonCreate as ComparisonCreateModel
from .model.comparison import ComparisonDetail as ComparisonDetailModel
from .model.comparison import ComparisonList as ComparisonListModel
from .model.comparison import ComparisonOverview as ComparisonOverviewModel
from .model.error import Error as ErrorModel
from .model.get_mappings_output import GetMappingsOutput
from .model.init_project_input import InitProjectInput
from .model.mapping import MappingBase as MappingBaseModel
from .model.mapping import MappingCreate as MappingCreateModel
from .model.mapping import MappingDetails as MappingDetailsModel
from .model.mapping import MappingUpdate as MappingUpdateModel
from .model.mapping import MappingField as MappingFieldModel
from .model.mapping import MappingFieldMinimal as MappingFieldMinimalModel
from .model.mapping import MappingFieldsOutput as MappingFieldsOutputModel
from .model.mapping_input import MappingInput
from .model.mapping_action_models import EvaluationResult
from .model.mapping_evaluation_model import (
  MappingEvaluationModel,
  MappingEvaluationSummaryModel,
)
from .model.transformation import (
    TransformationBase as TransformationBaseModel,
    TransformationCreate as TransformationCreateModel,
    TransformationDetails as TransformationDetailsModel,
    TransformationUpdate as TransformationUpdateModel,
    TransformationField as TransformationFieldModel,
    TransformationFieldMinimal as TransformationFieldMinimalModel,
    TransformationFieldsOutput as TransformationFieldsOutputModel,
    TransformationMappingLink as TransformationMappingLinkModel,
)
from .model.target_creation import (
    TargetCreationBase as TargetCreationBaseModel,
    TargetCreationCreate as TargetCreationCreateModel,
    TargetCreationDetails as TargetCreationDetailsModel,
    TargetCreationUpdate as TargetCreationUpdateModel,
    TargetCreationField as TargetCreationFieldModel,
    TargetCreationFieldMinimal as TargetCreationFieldMinimalModel,
    TargetCreationFieldsOutput as TargetCreationFieldsOutputModel,
    TargetCreationEvaluationSummary as TargetCreationEvaluationSummaryModel,
)
from .evaluation import StatusAggregator
from .model.package import Package as PackageModel
from .model.package import PackageInput as PackageInputModel
from .model.package import PackageList as PackageListModel
from .model.profile import ProfileList as ProfileListModel
from .model.profile import ProfileDetails as ProfileDetailsModel
from .model.project import Project as ProjectModel
from .model.project import ProjectInput as ProjectInputModel
from .model.project import ProjectList as ProjectListModel
from .manual_entries_migration import migrate_manual_entries
from .manual_entries_id_mapping import rewrite_manual_entries_ids_by_fhir_context
from .manual_entries import ManualEntries
from .fshMappingGenerator.fsh_mapping_main import (
  STRUCTUREMAP_PACKAGE_VERSION,
  build_structuremap_package,
  build_transformation_structuremap_artifact,
)
from .utils.structuremap_helpers import (
  get_safe_mapping_filename,
  get_safe_project_filename,
  sanitize_folder_name,
  alias_from_profile,
)


def _ensure_unique_filename(filename: str, used: set[str]) -> str:
    if filename not in used:
        used.add(filename)
        return filename

    stem, ext = os.path.splitext(filename)
    counter = 2
    while True:
        candidate = f"{stem}-{counter}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1

origins = ["http://localhost:4200", "http://127.0.0.1:4200"]
project_handler: ProjectsHandler
package_handler: PackageHandler
comparison_handler: ComparisonHandler
mapping_handler: MappingHandler
transformation_handler: TransformationHandler
target_creation_handler: TargetCreationHandler
cur_proj: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global project_handler
    global package_handler
    global comparison_handler
    global mapping_handler
    global transformation_handler
    global target_creation_handler

    # Set up
    project_handler = ProjectsHandler(
        Path(os.environ["STRUCTURE_COMPARER_PROJECTS_DIR"])
    )
    project_handler.load()

    package_handler = PackageHandler(project_handler)
    comparison_handler = ComparisonHandler(project_handler)
    mapping_handler = MappingHandler(project_handler)
    transformation_handler = TransformationHandler(project_handler)
    target_creation_handler = TargetCreationHandler(project_handler)

    # Let the app do its job
    yield

    # Tear down
    pass

app = FastAPI(title="Structure Comparer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def ping():
    return "pong"


@app.get("/projects", tags=["Projects"], deprecated=True)
async def get_projects_old():
    global project_handler
    return project_handler.keys


@app.get(
    "/project",
    tags=["Projects"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_project_list() -> ProjectListModel:
    global project_handler
    return project_handler.get_list()


@app.get(
    "/project/{project_key}",
    tags=["Projects"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_project(
    project_key: str, response: Response
) -> ProjectModel | ErrorModel:
    global project_handler

    try:
        proj = project_handler.get(project_key)
        return proj

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/init_project",
    tags=["Projects"],
    status_code=200,
    responses={400: {"error": {}}, 404: {"error": {}}},
    deprecated=True,
)
async def post_init_project(data: InitProjectInput, response: Response):
    global cur_proj

    if not data.project_name:
        response.status_code = 400
        return {"error": "Project name is required"}

    if data.project_name not in project_handler.keys:
        response.status_code = 404
        return {"error": "Project does not exist"}

    # Set current project name
    cur_proj = data.project_name

    return {"message": "Project initialized successfully"}


@app.post(
    "/create_project",
    tags=["Projects"],
    status_code=201,
    responses={400: {}, 409: {}},
    deprecated=True,
)
async def create_project_old(project_name: str, response: Response):

    if not project_name:
        response.status_code = 400
        return {"error": "Project name is required"}

    try:
        project_handler.update_or_create(project_name)

    except ProjectAlreadyExists as e:
        response.status_code = 409
        return {"error": str(e)}

    return {"message": "Project created successfully"}


@app.post(
    "/project/{project_key}",
    tags=["Projects"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def update_or_create_project(
    project_key: str, project: ProjectInputModel
) -> ProjectModel:
    global project_handler
    return project_handler.update_or_create(project_key, project)


@app.delete(
    "/project/{project_key}",
    tags=["Projects"],
    status_code=204,
    responses={404: {"model": ErrorModel}},
)
async def delete_project(project_key: str, response: Response) -> None:
    """Delete a project and all its data"""
    global project_handler
    try:
        project_handler.delete(project_key)
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/package",
    tags=["Packages"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def get_package_list(
    project_key: str, response: Response
) -> PackageListModel | ErrorModel:
    """
    Returns a list of the packages in the project
    """
    global package_handler
    try:
        pkg = package_handler.get_list(project_key)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return pkg


@app.post(
    "/project/{project_key}/package",
    tags=["Packages"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}, 409: {"error": {}}, 422: {"error": {}}},
)
async def post_package(
    project_key: str, file: UploadFile, response: Response
) -> PackageModel | ErrorModel:
    """
    Add a new package from the uploaded file

    The uploaded file needs to be valid FHIR package tarball and the profiles
    need to include snapshots.
    """
    global package_handler

    try:
        pkg = package_handler.new_from_file_upload(project_key, file)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except (InvalidFileFormat, PackageCorrupted, PackageNoSnapshots) as e:
        response.status_code = 422
        return ErrorModel.from_except(e)

    except PackageAlreadyExists as e:
        response.status_code = 409
        return ErrorModel.from_except(e)

    return pkg


@app.post(
    "/project/{project_key}/package/{package_id}",
    tags=["Packages"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {"error": {}}, 404: {"error": {}}},
)
async def update_package(
    project_key: str,
    package_id: str,
    package_input: PackageInputModel,
    response: Response,
) -> PackageModel | ErrorModel:
    """
    Update the information of a package
    """
    global package_handler
    try:
        pkg = package_handler.update(project_key, package_id, package_input)

    except (ProjectNotFound, PackageNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except NotAllowed as e:
        response.status_code = 400
        return ErrorModel.from_except(e)

    return pkg


@app.get(
    "/project/{project_key}/profile",
    tags=["Profiles"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def get_profile_list(
    project_key: str, response: Response
) -> ProfileListModel | ErrorModel:
    """
    Returns a list of all profiles in this project
    """
    global package_handler
    try:
        proj = package_handler.get_profiles(project_key)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return proj


@app.get(
    "/project/{project_key}/profile/{profile_id}",
    tags=["Profiles"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def get_profile_detail(
    project_key: str, profile_id: str, response: Response
) -> ProfileDetailsModel | ErrorModel:
    """
    Returns a single profile with all its field information
    """
    global package_handler
    try:
        profile = package_handler.get_profile(project_key, profile_id)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except PackageNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return profile


@app.get(
    "/project/{project_key}/comparison",
    tags=["Comparison"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def get_comparison_list(
    project_key: str, response: Response
) -> ComparisonListModel | ErrorModel:
    """
    Returns a list of all comparisons in this project
    """
    global comparison_handler
    try:
        comps = comparison_handler.get_list(project_key)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return comps


@app.post(
    "/project/{project_key}/comparison",
    tags=["Comparison"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {"error": {}}, 404: {"error": {}}},
)
async def create_comparison(
    project_key: str, input: ComparisonCreateModel, response: Response
) -> ComparisonOverviewModel | ErrorModel:
    """
    Creates a new comparison
    """
    global comparison_handler
    try:
        c = comparison_handler.create(project_key, input)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return c


@app.get(
    "/project/{project_key}/comparison/{comparison_id}",
    tags=["Comparison"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def get_comparison(
    project_key: str, comparison_id: str, response: Response
) -> ComparisonDetailModel | ErrorModel:
    """
    Get a comparison
    """
    global comparison_handler
    try:
        comp = comparison_handler.get(project_key, comparison_id)

    except (ProjectNotFound, ComparisonNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    return comp


@app.delete(
    "/project/{project_key}/comparison/{comparison_id}",
    tags=["Comparison"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {"error": {}}},
)
async def delete_comparison(project_key: str, comparison_id: str, response: Response):
    """
    Delete an existing comparison
    """
    global comparison_handler
    try:
        comparison_handler.delete(project_key, comparison_id)

    except (ProjectNotFound, ComparisonNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/action",
    tags=["Action"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_action_options() -> ActionOutputModel:
    """
    Get all classifications
    ---
    produces:
      - application/json
    responses:
      200:
        description: Classifications
        schema:
          required:
            - classifications
          properties:
            classifications:
              type: array
              items:
                type: object
                properties:
                  value:
                    type: string
                  remark:
                    type: string
                  instruction:
                    type: string
    """
    global project_handler
    return project_handler.get_action_options()


@app.get("/mappings", tags=["Mappings"], responses={412: {}}, deprecated=True)
async def get_mappings_old(response: Response) -> GetMappingsOutput | ErrorModel:
    """
    Get the available mappings
    Returns a list with all mappings, including the name and the url to access it.
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: OverviewMapping
          type: object
          required:
            - id
            - name
            - url
            - version
            - last_updated
            - status
            - sources
            - target
          properties:
            id:
              type: string
            name:
              type: string
            url:
              type: string
            version:
              type: string
            last_updated:
              type: string
            status:
              type: string
            sources:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                  profile_key:
                    type: string
                  simplifier_url:
                    type: string
                  version:
                    type: string
            target:
              type: object
              properties:
                name:
                  type: string
                profile_key:
                  type: string
                simplifier_url:
                  type: string
                version:
                  type: string
    responses:
      200:
        description: Available mappings
        schema:
          required:
            - mappings
          properties:
            mappings:
              type: array
              items:
                $ref: "#/async definitions/OverviewMapping"
    """
    global cur_proj, mapping_handler
    if cur_proj is None:
        response.status_code = 412
        return {"error": "Project needs to be initialized before accessing"}

    try:
        mappings = mapping_handler.get_list(cur_proj)
        return GetMappingsOutput(mappings=mappings)

    except ProjectNotFound:
        response.status_code = 404
        return ErrorModel(error="Project not found")


@app.get(
    "/project/{project_key}/mapping",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_mappings(
    project_key: str, response: Response
) -> GetMappingsOutput | ErrorModel:
    """
    Get the available mappings
    Returns a list with all mappings, including the name and the url to access it.
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: OverviewMapping
          type: object
          required:
            - id
            - name
            - url
            - version
            - last_updated
            - status
            - sources
            - target
          properties:
            id:
              type: string
            name:
              type: string
            url:
              type: string
            version:
              type: string
            last_updated:
              type: string
            status:
              type: string
            sources:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                  profile_key:
                    type: string
                  simplifier_url:
                    type: string
                  version:
                    type: string
            target:
              type: object
              properties:
                name:
                  type: string
                profile_key:
                  type: string
                simplifier_url:
                  type: string
                version:
                  type: string
    responses:
      200:
        description: Available mappings
        schema:
          required:
            - mappings
          properties:
            mappings:
              type: array
              items:
                $ref: "#/async definitions/OverviewMapping"
    """
    global mapping_handler
    try:
        mappings = mapping_handler.get_list(project_key)
        return GetMappingsOutput(mappings=mappings)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/mapping/{id}", tags=["Mappings"], responses={404: {}, 412: {}}, deprecated=True
)
async def get_mapping_old(id: str, response: Response) -> MappingBaseModel | ErrorModel:
    """
    Get a specific mapping
    Returns the mapping with the given id. This includes all details like classifications, presences in profiles, etc.
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: MappingFieldProfile
          type: object
          required:
            - name
            - present
          properties:
            name:
              type: string
            present:
                type: boolean
      - schema:
          id: MappingField
          required:
            - id
            - name
            - classification
            - profiles
            - remark
          type: object
          properties:
            id:
              type: string
            name:
              type: string
            classification:
              type: string
            classifications_allowed:
              type: array
              items:
                string
            extension:
              type: string
            extra:
              type: string
            profiles:
              type: array
              items:
                $ref: "#/async definitions/MappingFieldProfile"
            remark:
              type: string
      - schema:
          id: Mapping
          type: object
          required:
            - id
            - name
            - source_profiles
            - target_profile
            - fields
          properties:
            fields:
              type: array
              items:
                $ref: "#/async definitions/MappingField"
            id:
              type: string
            name:
              type: string
            source_profiles:
              type: array
              items:
                type: string
            target_profile:
              type: string
    parameters:
      - in: path
        name: id
        type: string
        required: true
        description: The id of the mapping
    responses:
      200:
        description: The mapping with the given id
        schema:
          $ref: "#/async definitions/Mapping"
      404:
        description: Mapping not found
    """
    global cur_proj, mapping_handler
    if cur_proj is None:
        response.status_code = 412
        return {"error": "Project needs to be initialized before accessing"}

    try:
        return mapping_handler.get(cur_proj, id)

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_mapping(
    project_key: str, mapping_id: str, response: Response
) -> MappingDetailsModel | ErrorModel:
    """
    Get the available mappings
    Returns a list with all mappings, including the name and the url to access it.
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: OverviewMapping
          type: object
          required:
            - id
            - name
            - url
            - version
            - last_updated
            - status
            - sources
            - target
          properties:
            id:
              type: string
            name:
              type: string
            url:
              type: string
            version:
              type: string
            last_updated:
              type: string
            status:
              type: string
            sources:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                  profile_key:
                    type: string
                  simplifier_url:
                    type: string
                  version:
                    type: string
            target:
              type: object
              properties:
                name:
                  type: string
                profile_key:
                  type: string
                simplifier_url:
                  type: string
                version:
                  type: string
    responses:
      200:
        description: Available mappings
        schema:
          required:
            - mappings
          properties:
            mappings:
              type: array
              items:
                $ref: "#/async definitions/OverviewMapping"
    """
    global mapping_handler
    try:
        return mapping_handler.get(project_key, mapping_id)

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/html",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_mapping_results(
    project_key: str,
    mapping_id: str,
    show_remarks: bool,
    show_warnings: bool,
    response: Response,
) -> FileResponse:  # MappingDetailsModel | ErrorModel:
    """
    Get a static HTML page with the mappings
    Returns a static HTML page with all mappings.
    ---
    produces:
      - text/html
    responses:
      200:
        description: A static HTML page with the mappings
        content:
          text/html:
            schema:
              type: string
              format: binary
        headers:
          Content-Disposition:
            description: The filename of the HTML file
            schema:
              type: string
              example: "mapping_results.html"
    """
    global mapping_handler
    try:
        return FileResponse(
            mapping_handler.get_html(
                project_key, mapping_id, show_remarks, show_warnings
            ),
            media_type="text/html",
        )

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/structuremap",
    tags=["Mappings", "StructureMap Export"],
    responses={404: {"model": ErrorModel}},
)
async def download_structuremap(
    project_key: str,
    mapping_id: str,
    response: Response,
):
    """
    Download FHIR StructureMap for a mapping.
    
    Returns a file containing a StructureMap RuleSet
    generated from the mapping's actions.
    
    Args:
        project_key: The project identifier
        mapping_id: The mapping identifier
        
    Returns:
        StructureMap file as text/plain with Content-Disposition header for download
        
    Raises:
        404: Project or mapping not found
    """
    
    global mapping_handler
    try:
        # Get the mapping with actions
        mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
        
        # Get actions
        actions = mapping.get_action_info_map()

        primary_source = mapping.sources[0] if mapping.sources else None
        source_alias = alias_from_profile(primary_source, "source")
        target_alias = alias_from_profile(mapping.target, "target")

        # Create a ruleset name from mapping ID
        ruleset_name = f"{mapping_id.replace('-', '_')}_structuremap"

        package = build_structuremap_package(
          mapping=mapping,
          actions=actions,
          source_alias=source_alias,
          target_alias=target_alias,
          ruleset_name=ruleset_name,
        )

        manifest = package.manifest(
          mapping_id=mapping_id,
          project_key=project_key,
          ruleset_name=ruleset_name,
          package_root=".",
        )

        buffer = io.BytesIO()
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
          # Write files directly without the package_root subfolder
          manifest_path = "manifest.json"
          zf.writestr(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))
          for artifact in package.artifacts:
            zf.writestr(artifact.filename, artifact.content)

        buffer.seek(0)
        
        # Create human-readable filename from mapping name and version
        filename = get_safe_mapping_filename(mapping, mapping_id)
        
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=buffer.read(), media_type="application/zip", headers=headers)
        
    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as e:
        logging.exception(f"Error generating StructureMap export: {str(e)}")
        response.status_code = 500
        return ErrorModel(error=f"StructureMap export failed: {str(e)}")


@app.get(
    "/project/{project_key}/structuremaps",
    tags=["Projects", "StructureMap Export"],
    responses={404: {"model": ErrorModel}},
)
async def download_project_structuremaps(
    project_key: str,
    response: Response,
):
    """
    Download all FHIR StructureMaps for every mapping and transformation in a project.
    
    Returns a ZIP file containing StructureMap packages for each mapping and
    standalone artifacts for each transformation. The archive stores all
    StructureMap JSON files in the root alongside a single manifest.json entry.
    
    Args:
        project_key: The project identifier
        
    Returns:
        ZIP file containing all StructureMap artifacts with Content-Disposition header for download
        
    Raises:
        404: Project not found
    """
    
    global mapping_handler
    try:
        # Get the project
        project = mapping_handler.project_handler._get(project_key)
        
        master_buffer = io.BytesIO()
        aggregated_entries: list[dict] = []
        used_filenames: set[str] = set()
        successful_mappings = 0
        failed_mappings: list[str] = []
        successful_transformations = 0
        failed_transformations: list[str] = []

        with ZipFile(master_buffer, mode="w", compression=ZIP_DEFLATED) as master_zip:
          for mapping_id in project.mappings.keys():
            try:
              mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
              actions = mapping.get_action_info_map()

              primary_source = mapping.sources[0] if mapping.sources else None
              source_alias = alias_from_profile(primary_source, "source")
              target_alias = alias_from_profile(mapping.target, "target")

              ruleset_name = f"{mapping_id.replace('-', '_')}_structuremap"

              package = build_structuremap_package(
                mapping=mapping,
                actions=actions,
                source_alias=source_alias,
                target_alias=target_alias,
                ruleset_name=ruleset_name,
              )

              successful_mappings += 1

              for artifact in package.artifacts:
                filename = _ensure_unique_filename(artifact.filename, used_filenames)
                master_zip.writestr(filename, artifact.content)
                aggregated_entries.append(artifact.manifest_entry(filename=filename))

            except Exception as e:
              logging.warning(f"Failed to generate StructureMap for mapping {mapping_id}: {str(e)}")
              failed_mappings.append(mapping_id)
              continue

          transformations = getattr(project, "transformations", {}) or {}
          for transformation_id, transformation in transformations.items():
            try:
              artifact = build_transformation_structuremap_artifact(
                transformation=transformation,
                project=project,
                ruleset_name=f"{transformation_id.replace('-', '_')}_structuremap",
              )
              filename = _ensure_unique_filename(artifact.filename, used_filenames)
              master_zip.writestr(filename, artifact.content)
              aggregated_entries.append(artifact.manifest_entry(filename=filename))
              successful_transformations += 1
            except Exception as e:
              logging.warning(
                "Failed to generate StructureMap for transformation %s: %s",
                transformation_id,
                str(e),
              )
              failed_transformations.append(transformation_id)

          combined_manifest = {
            "packageVersion": STRUCTUREMAP_PACKAGE_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "projectKey": project_key,
            "mappingCount": successful_mappings,
            "transformationCount": successful_transformations,
            "artifactCount": len(aggregated_entries),
            "failedMappings": failed_mappings or None,
            "failedTransformations": failed_transformations or None,
            "packageRoot": ".",
            "artifacts": aggregated_entries,
          }
          if combined_manifest["failedMappings"] is None:
            combined_manifest.pop("failedMappings")
          if combined_manifest["failedTransformations"] is None:
            combined_manifest.pop("failedTransformations")

          master_zip.writestr("manifest.json", json.dumps(combined_manifest, indent=2, ensure_ascii=False))

        master_buffer.seek(0)
        
        # Create human-readable filename from project name
        filename = get_safe_project_filename(project, project_key)
        
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=master_buffer.read(), media_type="application/zip", headers=headers)
        
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as e:
        logging.exception(f"Error generating project StructureMap export: {str(e)}")
        response.status_code = 500
        return ErrorModel(error=f"Project StructureMap export failed: {str(e)}")


@app.get(
    "/mapping/{id}/fields",
    tags=["Fields"],
    responses={404: {}, 412: {}},
    deprecated=True,
)
async def get_mapping_fields_old(
    id: str, response: Response
) -> MappingFieldsOutputModel | ErrorModel:
    """
    Get the fields of a mapping
    Returns a brief list of the fields
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: MappingFieldShort
          type: object
          reuqired:
            - id
            - name
          properties:
            id:
              type: string
            name:
              type: string
      - schema:
          id: MappingShort
          type: object
          required:
            - id
            - fields
          properties:
            fields:
              type: array
              items:
                $ref: "#/async definitions/MappingFieldShort"
            id:
              type: string
    parameters:
      - in: path
        name: id
        type: string
        required: true
        description: The id of the mapping
    responses:
      200:
        description: The fields of the mapping
        schema:
          $ref: "#/async definitions/MappingShort"
      404:
        description: Mapping not found
    """
    global cur_proj, mapping_handler
    if cur_proj is None:
        response.status_code = 412
        return {"error": "Project needs to be initialized before accessing"}

    try:
        return mapping_handler.get_field_list(cur_proj, id)

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/field",
    tags=["Fields"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_mapping_fields(
    project_key: str, mapping_id: str, response: Response
) -> MappingFieldsOutputModel | ErrorModel:
    """
    Get the fields of a mapping
    Returns a brief list of the fields
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: MappingFieldShort
          type: object
          reuqired:
            - id
            - name
          properties:
            id:
              type: string
            name:
              type: string
      - schema:
          id: MappingShort
          type: object
          required:
            - id
            - fields
          properties:
            fields:
              type: array
              items:
                $ref: "#/async definitions/MappingFieldShort"
            id:
              type: string
    parameters:
      - in: path
        name: id
        type: string
        required: true
        description: The id of the mapping
    responses:
      200:
        description: The fields of the mapping
        schema:
          $ref: "#/async definitions/MappingShort"
      404:
        description: Mapping not found
    """
    global mapping_handler
    try:
        return mapping_handler.get_field_list(project_key, mapping_id)

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/field/{field_name}",
    tags=["Fields"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_mapping_field(
    project_key: str, mapping_id: str, field_name: str, response: Response
) -> MappingFieldModel | ErrorModel:
    """
    Get the fields of a mapping
    Returns a brief list of the fields
    ---
    produces:
      - application/json
    async definitions:
      - schema:
          id: MappingFieldShort
          type: object
          reuqired:
            - id
            - name
          properties:
            id:
              type: string
            name:
              type: string
      - schema:
          id: MappingShort
          type: object
          required:
            - id
            - fields
          properties:
            fields:
              type: array
              items:
                $ref: "#/async definitions/MappingFieldShort"
            id:
              type: string
    parameters:
      - in: path
        name: id
        type: string
        required: true
        description: The id of the mapping
    responses:
      200:
        description: The fields of the mapping
        schema:
          $ref: "#/async definitions/MappingShort"
      404:
        description: Mapping not found
    """
    global mapping_handler
    try:
        return mapping_handler.get_field(project_key, mapping_id, field_name)

    except (ProjectNotFound, MappingNotFound, FieldNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/mapping",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {}, 404: {}},
)
async def post_mapping(
    project_key: str,
    mappingData: MappingCreateModel,
    response: Response,
) -> MappingDetailsModel | ErrorModel:
    """
    Post a new mapping for a project
    Creates a new mapping in the project with the given key.
    The mapping needs to be a valid MappingBaseModel.

    ---
    consumes:
      - application/json
    parameters:
      - in: path
        name: project_key
        type: string
        required: true
        description: The key of the project
    responses:
      200:
        description: The mapping was created
      400:
        description: There was something wrong with the request
        schema:
          properties:
            error:
              type: string
              description: An error message
      404:
        description: Project not found
    """
    global mapping_handler
    try:
        return mapping_handler.create_new(project_key, mappingData)

    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except (
        MappingActionNotAllowed,
        MappingTargetMissing,
        MappingTargetNotFound,
        MappingValueMissing,
    ) as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.patch(
    "/project/{project_key}/mapping/{mapping_id}",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def patch_mapping(
    project_key: str,
    mapping_id: str,
    update_data: MappingUpdateModel,
    response: Response,
) -> MappingDetailsModel | ErrorModel:
    """
    Update mapping metadata (status, version)
    
    Updates the metadata of an existing mapping such as status and version.
    The last_updated timestamp is automatically updated.
    
    Args:
        project_key: The unique identifier of the project
        mapping_id: The unique identifier of the mapping
        update_data: The fields to update
        
    Returns:
        The updated mapping details
        
    Raises:
        404: Project or mapping not found
    """
    global mapping_handler
    try:
        return mapping_handler.update(project_key, mapping_id, update_data)

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/mapping/{mapping_id}/field/{field_id}/classification",
    tags=["Fields"],
    responses={400: {}, 404: {}, 412: {}},
    deprecated=True,
)
async def post_mapping_field_classification_old(
    mapping_id: str, field_id: str, mapping: MappingInput, response: Response
):
    """
    Post a manual classification for a field
    Overrides the default action of a field.

    `action` selects the new action. `target` applies to copy actions. `value`
    transports fixed values when required.
    ---
    consumes:
      - application/json
    parameters:
      - in: path
        name: mapping_id
        type: string
        required: true
        description: The id of the mapping
      - in: path
        name: field_id
        type: string
        required: true
        description: The id of the field
      - in: body
        name: body
        schema:
          required:
            - action
          properties:
            action:
              type: string
              enum:
                - copy_from
                - copy_to
                - fixed
                - use
                - not_use
                - empty
              description: Which action should be performed
            target:
              type: string
              description: Field that is targetted (for copy actions)
            value:
              type: string
              description: The fixed value
    responses:
      200:
        description: The field was updated
      400:
        description: There was something wrong with the request
        schema:
          properties:
            error:
              type: string
              description: An error message
      404:
        description: Mapping or field not found
    """
    global cur_proj, mapping_handler
    if cur_proj is None:
        response.status_code = 412
        return {"error": "Project needs to be initialized before accessing"}

    try:
        return mapping_handler.set_field(cur_proj, mapping_id, field_id, mapping)

    except (ProjectNotFound, MappingNotFound, FieldNotFound) as e:
        response.status_code = 404
        return {"error": str(e)}

    except (
        MappingActionNotAllowed,
        MappingTargetMissing,
        MappingTargetNotFound,
        MappingValueMissing,
    ) as e:
        response.status_code = 400
        return {"error": str(e)}


@app.post(
    "/project/{project_key}/mapping/{mapping_id}/field/{field_name}",
    tags=["Fields"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {}, 404: {}},
)
async def post_mapping_field(
    project_key: str,
    mapping_id: str,
    field_name: str,
    mapping: MappingFieldMinimalModel,
    response: Response,
) -> MappingFieldModel | ErrorModel:
    """
    Post a manual classification for a field
    Overrides the default action of a field.

    `action` selects the new action. `target` applies to copy actions. `value`
    transports fixed values when required.
    ---
    consumes:
      - application/json
    parameters:
      - in: path
        name: mapping_id
        type: string
        required: true
        description: The id of the mapping
      - in: path
        name: field_id
        type: string
        required: true
        description: The id of the field
      - in: body
        name: body
        schema:
          required:
            - action
          properties:
            action:
              type: string
              enum:
                - copy_from
                - copy_to
                - fixed
                - use
                - not_use
                - empty
              description: Which action should be performed
            target:
              type: string
              description: Field that is targetted (for copy actions)
            value:
              type: string
              description: The fixed value
    responses:
      200:
        description: The field was updated
      400:
        description: There was something wrong with the request
        schema:
          properties:
            error:
              type: string
              description: An error message
      404:
        description: Mapping or field not found
    """
    global mapping_handler
    try:
        # Update the field
        mapping_handler.set_field(project_key, mapping_id, field_name, mapping)

        # Get the update data
        return mapping_handler.get_field(project_key, mapping_id, field_name)

    except (ProjectNotFound, MappingNotFound, FieldNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except (
        MappingActionNotAllowed,
        MappingTargetMissing,
        MappingTargetNotFound,
        MappingValueMissing,
    ) as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/mapping/{mapping_id}/field/{field_name}/apply-recommendation",
    tags=["mapping"],
    response_model=MappingFieldModel,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {}, 404: {}},
)
async def apply_recommendation(
    project_key: str,
    mapping_id: str,
    field_name: str,
    index: int = 0,
    response: Response = None,
) -> MappingFieldModel | ErrorModel:
    """
    Apply a recommendation to convert it into an active action.
    
    This endpoint:
    - Takes the recommendation at the specified index for a field
    - Converts it to a manual action
    - Persists it in manual_entries.yaml
    - Re-evaluates the mapping
    - Returns the updated field
    
    ---
    parameters:
      - in: path
        name: project_key
        type: string
        required: true
        description: The project key
      - in: path
        name: mapping_id
        type: string
        required: true
        description: The id of the mapping
      - in: path
        name: field_name
        type: string
        required: true
        description: The name of the field
      - in: query
        name: index
        type: integer
        default: 0
        description: Index of the recommendation to apply (0-based)
    responses:
      200:
        description: Recommendation was successfully applied
      404:
        description: Project, mapping, field, or recommendation not found
      400:
        description: Invalid request (e.g., invalid index)
    """
    global mapping_handler
    try:
        return mapping_handler.apply_recommendation(project_key, mapping_id, field_name, index)

    except (ProjectNotFound, MappingNotFound, FieldNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except Exception as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/mapping/{mapping_id}/field/{field_name}/apply-all-children-recommendations",
    tags=["mapping"],
    response_model=list[MappingFieldModel],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={400: {}, 404: {}},
)
async def apply_all_children_recommendations(
    project_key: str,
    mapping_id: str,
    field_name: str,
    response: Response = None,
) -> list[MappingFieldModel] | ErrorModel:
    """
    Apply all recommendations for all children of a parent field.
    
    This endpoint:
    - Gets all descendant fields of the parent
    - For each descendant that has recommendations, applies the first one
    - Persists all changes in manual_entries.yaml
    - Re-evaluates the mapping
    - Returns list of all updated fields
    
    This is useful when setting an extension action on a parent field
    and wanting to automatically apply the inherited recommendations
    to all children.
    
    ---
    parameters:
      - in: path
        name: project_key
        type: string
        required: true
        description: The project key
      - in: path
        name: mapping_id
        type: string
        required: true
        description: The id of the mapping
      - in: path
        name: field_name
        type: string
        required: true
        description: The parent field name
    responses:
      200:
        description: Recommendations were successfully applied to children
      404:
        description: Project, mapping, or field not found
      400:
        description: Invalid request
    """
    global mapping_handler
    try:
        return mapping_handler.apply_all_children_recommendations(project_key, mapping_id, field_name)

    except (ProjectNotFound, MappingNotFound, FieldNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)

    except Exception as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/evaluation",
    tags=["Mappings", "Evaluation"],
    response_model=MappingEvaluationModel,
    responses={404: {}, 412: {}},
)
async def get_mapping_evaluation(
    project_key: str, mapping_id: str, response: Response
) -> MappingEvaluationModel | ErrorModel:
    """Return evaluation data for each field within the mapping."""
    global mapping_handler
    try:
        mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
        evaluations = mapping.get_evaluation_map()
        summary = StatusAggregator.build_status_summary(evaluations)

        return MappingEvaluationModel(
            mapping_id=mapping_id,
            mapping_name=mapping.name,
            field_evaluations=evaluations,
            summary=summary,
        )

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/evaluation/summary",
    tags=["Mappings", "Evaluation"],
    response_model=MappingEvaluationSummaryModel,
    responses={404: {"model": ErrorModel}, 412: {"model": ErrorModel}},
)
async def get_mapping_evaluation_summary(
    project_key: str, mapping_id: str, response: Response
) -> MappingEvaluationSummaryModel | ErrorModel:
    """Return aggregated counters for the mapping evaluation."""
    global mapping_handler
    try:
        mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
        evaluations = mapping.get_evaluation_map()
        summary = StatusAggregator.build_status_summary(evaluations)

        return MappingEvaluationSummaryModel(
            mapping_id=mapping_id,
            mapping_name=mapping.name,
            **summary,
        )

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/mapping/{mapping_id}/field/{field_name}/evaluation",
    tags=["Fields", "Evaluation"],
    response_model=EvaluationResult,
    responses={404: {}, 412: {}},
)
async def get_field_evaluation(
    project_key: str, mapping_id: str, field_name: str, response: Response
) -> EvaluationResult | ErrorModel:
    """Return evaluation data for a single field."""
    global mapping_handler
    try:
        mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)

        if field_name not in mapping.fields:
            response.status_code = 404
            return ErrorModel(error="Field not found")

        evaluations = mapping.get_evaluation_map()
        evaluation = evaluations.get(field_name)

        if evaluation is None:
            response.status_code = 404
            return ErrorModel(error="Evaluation not available")

        return evaluation

    except (ProjectNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/manual-entries/import",
    tags=["Manual Entries"],
    responses={400: {"model": ErrorModel}, 404: {"model": ErrorModel}, 500: {"model": ErrorModel}},
)
async def import_manual_entries(
    project_key: str,
    file: UploadFile,
    response: Response,
) -> dict:
    """
    Import legacy manual_entries.yaml file into the project.
    
    Uploads and migrates an old manual_entries.yaml file to the current format.
    The migrated data will replace the current manual_entries.yaml in the project.
    
    Args:
        project_key: The project identifier
        file: The legacy manual_entries.yaml file to import
        
    Returns:
        Dictionary with import status and statistics
        
    Raises:
        404: Project not found
        400: No file uploaded, empty file, or invalid YAML format
        500: Import or migration failed
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Get the project
        global project_handler
        project = project_handler._get(project_key)
        
    except ProjectNotFound:
        response.status_code = 404
        return {"error": "Project not found"}
    
    try:
        # Check if file was uploaded
        if not file or not file.filename:
            response.status_code = 400
            return {"error": "No file uploaded or file is empty"}
        
        # Read the uploaded file
        file_content = await file.read()
        
        if not file_content:
            response.status_code = 400
            return {"error": "No file uploaded or file is empty"}
        
        # Parse YAML content
        try:
            legacy_data = yaml.safe_load(file_content.decode('utf-8'))
            if legacy_data is None:
                response.status_code = 400
                return {"error": "Invalid YAML format in uploaded file"}
                
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {str(e)}")
            response.status_code = 400
            return {"error": "Invalid YAML format in uploaded file"}
        except UnicodeDecodeError as e:
            logger.error(f"File encoding error: {str(e)}")
            response.status_code = 400
            return {"error": "Invalid file encoding, expected UTF-8"}
        
        # Migrate the legacy data to current format
        try:
            migrated_data = migrate_manual_entries(legacy_data)
            logger.info(f"Migration completed, {len(migrated_data.get('entries', []))} entries")
        except ValueError as e:
            logger.error(f"Migration failed: {str(e)}")
            response.status_code = 400
            return {"error": f"Migration failed: {str(e)}"}
        
        # Map legacy IDs to current mapping IDs based on FHIR context
        try:
            migrated_data, id_mapping_stats = rewrite_manual_entries_ids_by_fhir_context(
                project, legacy_data, migrated_data
            )
            logger.info(f"ID mapping completed: {id_mapping_stats['mapped_entries']} mapped, "
                        f"{id_mapping_stats['unmapped_entries']} unmapped")
            
            if id_mapping_stats['warnings']:
                for warning in id_mapping_stats['warnings']:
                    logger.warning(warning)
        except Exception as e:
            logger.error(f"ID mapping failed: {str(e)}")
            response.status_code = 500
            return {"error": f"ID mapping failed: {str(e)}"}
        
        # Calculate statistics before writing
        imported_entries = len(migrated_data.get("entries", []))
        total_fields = sum(len(entry.get("fields", [])) for entry in migrated_data.get("entries", []))
        logger.info(f"About to write {imported_entries} entries with {total_fields} total fields")
        logger.info(f"Migrated data sample: {str(migrated_data)[:500]}...")
        
        # Create new ManualEntries object and write to project
        manual_entries_file = project.dir / project.config.manual_entries_file
        
        # Create ManualEntries object from migrated data
        from .model.manual_entries import ManualEntries as ManualEntriesModel
        manual_entries = ManualEntries()
        manual_entries._data = ManualEntriesModel.model_validate(migrated_data)
        manual_entries._file = manual_entries_file
        
        # Write the new manual_entries.yaml
        manual_entries.write()
        logger.info(f"Successfully wrote manual_entries.yaml to {manual_entries_file}")
        
        # Reload the project's manual entries to reflect changes
        project._Project__read_manual_entries()
        logger.info(f"Reloaded project manual entries, now has {len(project.manual_entries.entries)} entries")
        
        logger.info(f"Successfully imported manual_entries for project {project_key}: "
                    f"{imported_entries} mappings, {total_fields} fields")
        
        return {
            "status": "ok",
            "message": "Import completed successfully",
            "project_key": project_key,
            "imported_entries": imported_entries,
            "imported_fields": total_fields,
            "filename": file.filename,
            "id_mapping": {
                "mapped_entries": id_mapping_stats['mapped_entries'],
                "unmapped_entries": id_mapping_stats['unmapped_entries'],
                "warnings_count": len(id_mapping_stats['warnings']),
                "mappings": id_mapping_stats['mappings']
            }
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error during import: {str(e)}")
        response.status_code = 500
        return {"error": f"Import failed: {str(e)}"}


# ============================================================================
# Migration Endpoints
# ============================================================================

@app.post(
    "/project/{project_key}/migrate",
    tags=["Migration"],
    responses={404: {}},
)
async def migrate_project(
    project_key: str, response: Response
) -> dict | ErrorModel:
    """
    Migrate a project's config.json and manual_entries.yaml to v2 format.
    
    This adds the 'transformations' array to config.json if missing.
    The manual_entries.yaml format is preserved (backwards compatible).
    """
    global project_handler
    try:
        from .migration.config_migration import migrate_config_to_v2, detect_config_version
        import json
        
        project = project_handler._get(project_key)
        if project is None:
            raise ProjectNotFound()
        
        config_file = project.dir / "config.json"
        
        # Read current config
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        original_version = detect_config_version(config)
        
        if original_version == '2.0':
            return {
                "status": "already_migrated",
                "message": "Project config is already in v2 format",
                "project_key": project_key,
                "config_version": "2.0"
            }
        
        # Migrate config
        migrated_config = migrate_config_to_v2(config)
        
        # Write migrated config
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(migrated_config, f, indent=2, ensure_ascii=False)
        
        # Reload project config
        from .data.config import ProjectConfig
        project.config = ProjectConfig.from_json(config_file)
        
        return {
            "status": "migrated",
            "message": "Project config migrated to v2 format",
            "project_key": project_key,
            "config_version": "2.0",
            "changes": ["Added 'transformations' array to config.json"]
        }
        
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as e:
        logger.exception(f"Migration failed: {str(e)}")
        response.status_code = 500
        return {"error": f"Migration failed: {str(e)}"}


@app.post(
    "/migrate/all",
    tags=["Migration"],
)
async def migrate_all_projects(response: Response) -> dict:
    """
    Migrate all projects to v2 format.
    Migrates both config.json (adds transformations array) and 
    manual_entries.yaml (renames entries to mapping_entries).
    """
    global project_handler
    from .migration.config_migration import migrate_config_to_v2, detect_config_version
    import json
    
    results = []
    
    for project_key in project_handler.keys:
        try:
            project = project_handler._get(project_key)
            changes = []
            
            # --- Migrate config.json ---
            config_file = project.dir / "config.json"
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            config_version = detect_config_version(config)
            
            if config_version == '1.0':
                migrated_config = migrate_config_to_v2(config)
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(migrated_config, f, indent=2, ensure_ascii=False)
                
                # Reload project config
                from .data.config import ProjectConfig
                project.config = ProjectConfig.from_json(config_file)
                changes.append("config.json: Added 'transformations' array")
            
            # --- Migrate manual_entries.yaml ---
            manual_entries_file = project.dir / project.config.manual_entries_file
            
            if manual_entries_file.exists():
                with open(manual_entries_file, 'r', encoding='utf-8') as f:
                    manual_content = yaml.safe_load(f) or {}
                
                # Check if migration is needed (has 'entries' but no 'mapping_entries')
                has_legacy_entries = 'entries' in manual_content and manual_content['entries']
                has_new_format = 'mapping_entries' in manual_content and manual_content['mapping_entries']
                
                if has_legacy_entries and not has_new_format:
                    # Migrate: move entries to mapping_entries
                    migrated_manual = {
                        'transformation_entries': manual_content.get('transformation_entries', []),
                        'mapping_entries': manual_content['entries'],
                    }
                    
                    with open(manual_entries_file, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(migrated_manual, f, default_flow_style=False, allow_unicode=True)
                    
                    # Reload manual entries
                    project._Project__read_manual_entries()
                    changes.append("manual_entries.yaml: Renamed 'entries' to 'mapping_entries', added 'transformation_entries'")
                elif not has_legacy_entries and not has_new_format:
                    # Empty file - add new format structure
                    migrated_manual = {
                        'transformation_entries': [],
                        'mapping_entries': [],
                    }
                    
                    with open(manual_entries_file, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(migrated_manual, f, default_flow_style=False, allow_unicode=True)
                    
                    project._Project__read_manual_entries()
                    changes.append("manual_entries.yaml: Initialized with v2 format")
            
            if changes:
                results.append({
                    "project": project_key,
                    "status": "migrated",
                    "changes": changes
                })
            else:
                results.append({
                    "project": project_key,
                    "status": "already_migrated"
                })
            
        except Exception as e:
            results.append({
                "project": project_key,
                "status": "error",
                "error": str(e)
            })
    
    migrated_count = sum(1 for r in results if r["status"] == "migrated")
    already_migrated_count = sum(1 for r in results if r["status"] == "already_migrated")
    error_count = sum(1 for r in results if r["status"] == "error")
    
    return {
        "status": "completed",
        "summary": {
            "total": len(results),
            "migrated": migrated_count,
            "already_migrated": already_migrated_count,
            "errors": error_count
        },
        "results": results
    }


# ============================================================================
# Transformation Endpoints
# ============================================================================

@app.get(
    "/project/{project_key}/transformation",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_transformations(
    project_key: str, response: Response
) -> list[TransformationBaseModel] | ErrorModel:
    """
    Get all transformations for a project.
    Returns a list of all transformations with their metadata.
    """
    global transformation_handler
    try:
        return transformation_handler.get_list(project_key)
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/transformation/{transformation_id}",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_transformation(
    project_key: str, transformation_id: str, response: Response
) -> TransformationDetailsModel | ErrorModel:
    """
    Get a specific transformation with all details including fields and linked mappings.
    """
    global transformation_handler
    try:
        return transformation_handler.get(project_key, transformation_id)
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/transformation/{transformation_id}/structuremap",
    tags=["Transformations", "StructureMap Export"],
    responses={404: {"model": ErrorModel}},
)
async def download_transformation_structuremap(
    project_key: str,
    transformation_id: str,
    response: Response,
):
    """Download a StructureMap ZIP for a transformation."""

    global transformation_handler
    try:
        project = transformation_handler.project_handler._get(project_key)
        transformation = transformation_handler._get_transformation(project_key, transformation_id, project)

        ruleset_name = f"{transformation_id.replace('-', '_')}_structuremap"
        artifact = build_transformation_structuremap_artifact(
            transformation=transformation,
            project=project,
            ruleset_name=ruleset_name,
        )

        manifest = {
            "packageVersion": STRUCTUREMAP_PACKAGE_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "projectKey": project_key,
            "transformationId": transformation_id,
            "rulesetName": artifact.ruleset_name,
            "packageRoot": ".",
            "artifacts": [artifact.manifest_entry()],
        }

        buffer = io.BytesIO()
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            zf.writestr(artifact.filename, artifact.content)

        buffer.seek(0)
        safe_name = sanitize_folder_name(getattr(transformation, "name", None) or transformation_id)
        filename = f"{safe_name}_transformation_structuremap.zip"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=buffer.read(), media_type="application/zip", headers=headers)

    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as exc:  # noqa: BLE001 - log unexpected export errors
        logging.exception("Error generating transformation StructureMap export: %s", exc)
        response.status_code = 500
        return ErrorModel(error=f"Transformation StructureMap export failed: {str(exc)}")


@app.post(
    "/project/{project_key}/transformation",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def create_transformation(
    project_key: str,
    transformation: TransformationCreateModel,
    response: Response,
) -> TransformationDetailsModel | ErrorModel:
    """
    Create a new transformation.
    """
    global transformation_handler
    try:
        return transformation_handler.create(project_key, transformation)
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as e:
        response.status_code = 500
        return ErrorModel(error=str(e))


@app.patch(
    "/project/{project_key}/transformation/{transformation_id}",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def update_transformation(
    project_key: str,
    transformation_id: str,
    update_data: TransformationUpdateModel,
    response: Response,
) -> TransformationDetailsModel | ErrorModel:
    """
    Update transformation metadata (status, version, profile information).
    """
    global transformation_handler
    try:
        return transformation_handler.update(project_key, transformation_id, update_data)
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.delete(
    "/project/{project_key}/transformation/{transformation_id}",
    tags=["Transformations"],
    responses={404: {}},
)
async def delete_transformation(
    project_key: str, transformation_id: str, response: Response
) -> dict | ErrorModel:
    """
    Delete a transformation.
    """
    global transformation_handler
    try:
        transformation_handler.delete(project_key, transformation_id)
        return {"status": "deleted", "id": transformation_id}
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/transformation/{transformation_id}/field",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_transformation_fields(
    project_key: str, transformation_id: str, response: Response
) -> TransformationFieldsOutputModel | ErrorModel:
    """
    Get all fields for a transformation.
    """
    global transformation_handler
    try:
        return transformation_handler.get_field_list(project_key, transformation_id)
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Get a specific field from a transformation.
    """
    global transformation_handler
    try:
        return transformation_handler.get_field(project_key, transformation_id, field_name)
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.put(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def set_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    input: TransformationFieldMinimalModel,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Set or update a field in a transformation.
    """
    global transformation_handler
    try:
        transformation_handler.set_field(project_key, transformation_id, field_name, input)
        return transformation_handler.get_field(project_key, transformation_id, field_name)
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except (MappingTargetNotFound, MappingTargetMissing, MappingValueMissing) as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}/link-mapping",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def link_mapping_to_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    link_data: TransformationMappingLinkModel,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Link a mapping to a transformation field.
    This creates a reference from the transformation field to a child mapping.
    """
    global transformation_handler
    try:
        return transformation_handler.link_mapping(
            project_key, transformation_id, field_name, link_data
        )
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except (FieldNotFound, MappingNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.delete(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}/link-mapping",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def unlink_mapping_from_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Remove a mapping link from a transformation field.
    """
    global transformation_handler
    try:
        return transformation_handler.unlink_mapping(
            project_key, transformation_id, field_name
        )
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}/link-target-creation",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def link_target_creation_to_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    target_creation_id: str,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Link a target creation to a transformation field.
    This creates a reference from the transformation field to a target creation.
    
    Body should be a string containing the target creation ID.
    """
    global transformation_handler
    try:
        return transformation_handler.link_target_creation(
            project_key, transformation_id, field_name, target_creation_id
        )
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except (FieldNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.delete(
    "/project/{project_key}/transformation/{transformation_id}/field/{field_name:path}/link-target-creation",
    tags=["Transformations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def unlink_target_creation_from_transformation_field(
    project_key: str,
    transformation_id: str,
    field_name: str,
    response: Response,
) -> TransformationFieldModel | ErrorModel:
    """
    Remove a target creation link from a transformation field.
    """
    global transformation_handler
    try:
        return transformation_handler.unlink_target_creation(
            project_key, transformation_id, field_name
        )
    except (ProjectNotFound, TransformationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


# ============================================================================
# TARGET CREATION ENDPOINTS
# Phase 5, Step 5.1: Router erstellen ✅
# Created: 2025-12-03
# ============================================================================


@app.get(
    "/project/{project_key}/target-creation",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_target_creations(
    project_key: str, response: Response
) -> list[TargetCreationBaseModel] | ErrorModel:
    """
    Get all target creations for a project.
    Returns a list of all target creations with their metadata and status counts.
    """
    global target_creation_handler
    try:
        return target_creation_handler.get_list(project_key)
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/target-creation/{target_creation_id}",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_target_creation(
    project_key: str, target_creation_id: str, response: Response
) -> TargetCreationDetailsModel | ErrorModel:
    """
    Get a specific target creation with all details including fields.
    """
    global target_creation_handler
    try:
        return target_creation_handler.get(project_key, target_creation_id)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.post(
    "/project/{project_key}/target-creation",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def create_target_creation(
    project_key: str,
    target_creation: TargetCreationCreateModel,
    response: Response,
) -> TargetCreationDetailsModel | ErrorModel:
    """
    Create a new target creation.
    Only requires a target profile (no source profiles).
    """
    global target_creation_handler
    try:
        return target_creation_handler.create(project_key, target_creation)
    except ProjectNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except Exception as e:
        response.status_code = 500
        return ErrorModel(error=str(e))


@app.patch(
    "/project/{project_key}/target-creation/{target_creation_id}",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def update_target_creation(
    project_key: str,
    target_creation_id: str,
    update_data: TargetCreationUpdateModel,
    response: Response,
) -> TargetCreationDetailsModel | ErrorModel:
    """
    Update target creation metadata (status, version, target profile information).
    """
    global target_creation_handler
    try:
        return target_creation_handler.update(project_key, target_creation_id, update_data)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.delete(
    "/project/{project_key}/target-creation/{target_creation_id}",
    tags=["Target Creations"],
    responses={404: {}},
)
async def delete_target_creation(
    project_key: str, target_creation_id: str, response: Response
) -> dict | ErrorModel:
    """
    Delete a target creation.
    """
    global target_creation_handler
    try:
        target_creation_handler.delete(project_key, target_creation_id)
        return {"status": "deleted", "id": target_creation_id}
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/target-creation/{target_creation_id}/field",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_target_creation_fields(
    project_key: str, target_creation_id: str, response: Response
) -> TargetCreationFieldsOutputModel | ErrorModel:
    """
    Get all fields for a target creation.
    """
    global target_creation_handler
    try:
        return target_creation_handler.get_field_list(project_key, target_creation_id)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/target-creation/{target_creation_id}/field/{field_name:path}",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_target_creation_field(
    project_key: str,
    target_creation_id: str,
    field_name: str,
    response: Response,
) -> TargetCreationFieldModel | ErrorModel:
    """
    Get a specific field from a target creation.
    """
    global target_creation_handler
    try:
        return target_creation_handler.get_field(project_key, target_creation_id, field_name)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


@app.put(
    "/project/{project_key}/target-creation/{target_creation_id}/field/{field_name:path}",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def set_target_creation_field(
    project_key: str,
    target_creation_id: str,
    field_name: str,
    input: TargetCreationFieldMinimalModel,
    response: Response,
) -> TargetCreationFieldModel | ErrorModel:
    """
    Set or update a field in a target creation.
    Only 'manual' and 'fixed' actions are allowed.
    """
    global target_creation_handler
    try:
        target_creation_handler.set_field(project_key, target_creation_id, field_name, input)
        return target_creation_handler.get_field(project_key, target_creation_id, field_name)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except FieldNotFound as e:
        response.status_code = 404
        return ErrorModel.from_except(e)
    except MappingValueMissing as e:
        response.status_code = 400
        return ErrorModel.from_except(e)


@app.get(
    "/project/{project_key}/target-creation/{target_creation_id}/evaluation/summary",
    tags=["Target Creations"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    responses={404: {}},
)
async def get_target_creation_evaluation_summary(
    project_key: str, target_creation_id: str, response: Response
) -> TargetCreationEvaluationSummaryModel | ErrorModel:
    """
    Get evaluation summary for a target creation.
    Returns counts of fields by status (action_required, resolved, optional_pending).
    """
    global target_creation_handler
    try:
        return target_creation_handler.get_evaluation_summary(project_key, target_creation_id)
    except (ProjectNotFound, TargetCreationNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


def serve():
    # Configure logging to show our application logs
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s:%(name)s: %(message)s'
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")


if __name__ == "__main__":
    serve()
