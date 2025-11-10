import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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
from .model.mapping import MappingDetails as MappingDetailsModel
from .model.mapping import MappingField as MappingFieldModel
from .model.mapping import MappingFieldMinimal as MappingFieldMinimalModel
from .model.mapping import MappingFieldsOutput as MappingFieldsOutputModel
from .model.mapping_input import MappingInput
from .model.package import Package as PackageModel
from .model.package import PackageInput as PackageInputModel
from .model.package import PackageList as PackageListModel
from .model.profile import ProfileList as ProfileListModel
from .model.project import Project as ProjectModel
from .model.project import ProjectInput as ProjectInputModel
from .model.project import ProjectList as ProjectListModel

origins = ["http://localhost:4200"]
project_handler: ProjectsHandler
package_handler: PackageHandler
comparison_handler: ComparisonHandler
mapping_handler: MappingHandler
cur_proj: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global project_handler
    global package_handler
    global comparison_handler
    global mapping_handler

    # Set up
    project_handler = ProjectsHandler(
        Path(os.environ["STRUCTURE_COMPARER_PROJECTS_DIR"])
    )
    project_handler.load()

    package_handler = PackageHandler(project_handler)
    comparison_handler = ComparisonHandler(project_handler)
    mapping_handler = MappingHandler(project_handler)

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


@app.delete(
    "/project/{project_key}/package/{package_id}",
    tags=["Packages"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=200,
    responses={404: {"error": {}}},
)
async def delete_package(
    project_key: str, package_id: str, response: Response
) -> None | ErrorModel:
    """
    Delete a package
    """
    global package_handler
    try:
        package_handler.delete(project_key, package_id)

    except (ProjectNotFound, PackageNotFound) as e:
        response.status_code = 404
        return ErrorModel.from_except(e)


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


@app.delete(
    "/project/{project_key}/mapping/{mapping_id}",
    tags=["Mappings"],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=200,
    responses={404: {}},
)
async def delete_mapping(
    project_key: str, mapping_id: str, response: Response
) -> None | ErrorModel:
    """
    Delete a mapping
    """
    global mapping_handler
    try:
        mapping_handler.delete(project_key, mapping_id)

    except (ProjectNotFound, MappingNotFound) as e:
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
    Overrides the async default action of a field. `action` that should set for the field, `target` is the target of copy action and `value` may be a fixed value.
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
    Overrides the async default action of a field. `action` that should set for the field, `target` is the target of copy action and `value` may be a fixed value.
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


def serve():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    serve()
