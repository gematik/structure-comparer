import logging
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError

from .action import Action
from .data.project import Project
from .errors import (
    FieldNotFound,
    MappingNotFound,
    MappingTargetMissing,
    MappingTargetNotFound,
    MappingValueMissing,
    PackageNotFound,
    ProjectNotFound,
)
from .helpers import get_field_by_name
from .model.action import ActionOutput as ActionOutputModel
from .model.mapping import MappingBase as MappingBaseModel
from .model.mapping import MappingDetails as MappingDetailsModel
from .model.mapping import MappingField as MappingFieldModel
from .model.mapping import MappingFieldBase as MappingFieldBaseModel
from .model.mapping import MappingFieldMinimal as MappingFieldMinimalModel
from .model.mapping import MappingFieldsOutput as MappingFieldsOutputModel
from .model.package import Package as PackageModel
from .model.package import PackageInput as PackageInputModel
from .model.package import PackageList as PackageListModel
from .model.profile import ProfileList as ProfileListModel
from .model.project import Project as ProjectModel
from .model.project import ProjectInput as ProjectInputModel
from .model.project import ProjectList as ProjectListModel

logger = logging.getLogger(__name__)


class ProjectsHandler:
    def __init__(self, projects_dir: Path):
        self.__projs_dir = projects_dir
        self.__projs: Dict[str, Project] = None

    @property
    def project_keys(self) -> List[str]:
        return list(self.__projs.keys())

    def load_projects(self) -> None:
        self.__projs = {}

        for path in self.__projs_dir.iterdir():
            # Only handle directories
            if path.is_dir():
                try:
                    self.__projs[path.name] = Project(path)
                except ValidationError as e:
                    logger.error(e.errors())
                    raise e

    def get_project_list(self) -> ProjectListModel:
        projects = [p.to_overview_model() for p in self.__projs.values()]
        return ProjectListModel(projects=projects)

    def get_project(self, project_key: str) -> ProjectModel:
        proj = self.__projs.get(project_key)

        if proj is None:
            raise ProjectNotFound()

        return proj.to_model()

    def update_or_create_project(
        self, proj_key: str, input: ProjectInputModel
    ) -> ProjectModel:

        # Check if update
        if proj := self.__projs.get(proj_key):
            proj.name = input.name

        # Create new one otherwise
        else:
            project_path = self.__projs_dir / proj_key

            # Load the newly created project
            proj = Project.create(project_path, input.name)
            self.__projs[proj_key] = proj

        return proj.to_model()

    def get_project_packages(self, proj_key: str) -> PackageListModel:
        proj = self.__projs.get(proj_key)

        if proj is None:
            raise ProjectNotFound()

        pkgs = [p.to_model() for p in proj.pkgs]
        return PackageListModel(packages=pkgs)

    def update_project_package(
        self, proj_key: str, package_id: str, package_input: PackageInputModel
    ) -> PackageModel:
        proj = self.__projs.get(proj_key)

        if proj is None:
            raise ProjectNotFound()

        pkg = proj.get_package(package_id)

        if pkg is None:
            raise PackageNotFound()

        # Update package information
        pkg.display = package_input.display

        return pkg

    def get_project_profiles(self, proj_key: str) -> ProfileListModel:
        proj = self.__projs.get(proj_key)

        if proj is None:
            raise ProjectNotFound()

        profs = [prof.to_pkg_model() for pkg in proj.pkgs for prof in pkg.profiles]
        return ProfileListModel(profiles=profs)

    @staticmethod
    def get_action_options() -> ActionOutputModel:
        return ActionOutputModel.from_enum()

    def get_mappings(self, project_key: str) -> List[MappingBaseModel]:
        proj = self.__projs.get(project_key)

        if proj is None:
            raise ProjectNotFound()

        return [comp.to_base_model() for comp in proj.mappings.values()]

    def get_mapping(self, project_key: str, mapping_id: str) -> MappingDetailsModel:
        mapping = self.__get_mapping(project_key, mapping_id)
        return mapping.to_details_model()

    def get_mapping_fields(
        self, project_key: str, mapping_id: str
    ) -> MappingFieldsOutputModel:
        mapping = self.__get_mapping(project_key, mapping_id)

        fields = [f.to_model() for f in mapping.fields.values()]

        return MappingFieldsOutputModel(id=mapping_id, fields=fields)

    def get_mapping_field(
        self, project_key: str, mapping_id: str, field_name: str
    ) -> MappingFieldsOutputModel:
        mapping = self.__get_mapping(project_key, mapping_id)

        field = get_field_by_name(mapping, field_name)

        if field is None:
            raise FieldNotFound()

        return field.to_model()

    def set_mapping_field(
        self,
        project_key: str,
        mapping_id: str,
        field_name: str,
        input: MappingFieldMinimalModel,
    ) -> MappingFieldModel:
        proj = self.__projs.get(project_key)

        # Easiest way to get the fields is from mapping
        mapping = self.__get_mapping(project_key, mapping_id, proj)
        field = get_field_by_name(mapping, field_name)

        if field is None:
            raise FieldNotFound()

        # Check if action is allowed for this field
        if input.action not in field.actions_allowed:
            raise MappingNotFound(
                f"action '{input.action.value}' not allowed for this field, allowed: {
                    ', '.join([field.value for field in field.actions_allowed])}"
            )

        # Build the entry that should be created/updated
        new_entry = MappingFieldBaseModel(name=field.name, action=input.action)
        if new_entry.action == Action.COPY_FROM or new_entry.action == Action.COPY_TO:
            if target_id := input.other:
                target = get_field_by_name(mapping, target_id)

                if target is None:
                    raise MappingTargetNotFound()

                new_entry.other = target.name
            else:
                raise MappingTargetMissing()
        elif new_entry.action == Action.FIXED:
            if fixed := input.fixed:
                new_entry.fixed = fixed
            else:
                raise MappingValueMissing()

        # Clean up possible manual entry this was copied from before
        manual_entries = proj.manual_entries[mapping_id]
        if (manual_entry := manual_entries.get(field.name)) and (
            manual_entry.action in [Action.COPY_FROM, Action.COPY_TO]
        ):
            del manual_entries[manual_entry.other]

        # Apply the manual entry
        manual_entries[field.name] = new_entry

        # Handle the partner entry for copy actions
        if new_entry.action == Action.COPY_FROM:
            manual_entries[target.name] = MappingFieldBaseModel(
                name=target.name, action=Action.COPY_TO, other=field.name
            )
        elif new_entry.action == Action.COPY_TO:
            manual_entries[target.name] = MappingFieldBaseModel(
                name=target.name, action=Action.COPY_FROM, other=field.name
            )
        # Save the changes
        proj.manual_entries.write()

        return True

    def __get_mapping(self, project_key, mapping_id, proj: Project = None):
        if proj is None:
            proj = self.__projs.get(project_key)

        if proj is None:
            raise ProjectNotFound()

        mapping = proj.mappings.get(mapping_id)

        if not mapping:
            raise MappingNotFound()

        mapping.fill_action_remark(proj.manual_entries)

        return mapping
