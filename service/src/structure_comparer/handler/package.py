from ..errors import PackageNotFound
from ..model.package import Package as PackageModel
from ..model.package import PackageInput as PackageInputModel
from ..model.package import PackageList as PackageListModel
from ..model.profile import ProfileList as ProfileListModel
from .project import ProjectsHandler


class PackageHandler:
    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, proj_key: str) -> PackageListModel:
        proj = self.project_handler._get(proj_key)
        pkgs = [p.to_model() for p in proj.pkgs]
        return PackageListModel(packages=pkgs)

    def update(
        self, proj_key: str, package_id: str, package_input: PackageInputModel
    ) -> PackageModel:
        proj = self.project_handler._get(proj_key)
        pkg = proj.get_package(package_id)

        if pkg is None:
            raise PackageNotFound()

        # Update package information
        pkg.display = package_input.display

        return pkg

    def get_profiles(self, proj_key: str) -> ProfileListModel:
        proj = self.project_handler._get(proj_key)

        profs = [prof.to_pkg_model() for pkg in proj.pkgs for prof in pkg.profiles]
        return ProfileListModel(profiles=profs)
