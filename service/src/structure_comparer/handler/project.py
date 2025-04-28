import logging
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError

from ..data.project import Project
from ..errors import PackageNotFound, ProjectNotFound
from ..model.action import ActionOutput as ActionOutputModel
from ..model.package import Package as PackageModel
from ..model.package import PackageInput as PackageInputModel
from ..model.package import PackageList as PackageListModel
from ..model.profile import ProfileList as ProfileListModel
from ..model.project import Project as ProjectModel
from ..model.project import ProjectInput as ProjectInputModel
from ..model.project import ProjectList as ProjectListModel

logger = logging.getLogger(__name__)


class ProjectsHandler:
    def __init__(self, projects_dir: Path):
        self.__projs_dir = projects_dir
        self.__projs: Dict[str, Project] = None

    @property
    def keys(self) -> List[str]:
        return list(self.__projs.keys())

    def load(self) -> None:
        self.__projs = {}

        for path in self.__projs_dir.iterdir():
            # Only handle directories
            if path.is_dir():
                try:
                    self.__projs[path.name] = Project(path)
                except ValidationError as e:
                    logger.error(e.errors())
                    raise e

    def get_list(self) -> ProjectListModel:
        projects = [p.to_overview_model() for p in self.__projs.values()]
        return ProjectListModel(projects=projects)

    def _get(self, project_key: str) -> Project:
        proj = self.__projs.get(project_key)

        if proj is None:
            raise ProjectNotFound()

        return proj

    def get(self, project_key: str) -> ProjectModel:
        proj = self._get(project_key)
        return proj.to_model()

    def update_or_create(self, proj_key: str, input: ProjectInputModel) -> ProjectModel:

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
        proj = self._get(proj_key)
        pkgs = [p.to_model() for p in proj.pkgs]
        return PackageListModel(packages=pkgs)

    def update_project_package(
        self, proj_key: str, package_id: str, package_input: PackageInputModel
    ) -> PackageModel:
        proj = self._get(proj_key)
        pkg = proj.get_package(package_id)

        if pkg is None:
            raise PackageNotFound()

        # Update package information
        pkg.display = package_input.display

        return pkg

    def get_project_profiles(self, proj_key: str) -> ProfileListModel:
        proj = self._get(proj_key)

        profs = [prof.to_pkg_model() for pkg in proj.pkgs for prof in pkg.profiles]
        return ProfileListModel(profiles=profs)

    @staticmethod
    def get_action_options() -> ActionOutputModel:
        return ActionOutputModel.from_enum()
