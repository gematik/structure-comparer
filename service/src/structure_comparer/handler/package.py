import json
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile

from ..errors import (
    InvalidFileFormat,
    PackageAlreadyExists,
    PackageCorrupted,
    PackageNotFound,
)
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

        return pkg.to_model()

    def get_profiles(self, proj_key: str) -> ProfileListModel:
        proj = self.project_handler._get(proj_key)

        profs = [prof.to_pkg_model() for pkg in proj.pkgs for prof in pkg.profiles]
        return ProfileListModel(profiles=profs)

    def new_from_file_upload(self, proj_key: str, file: UploadFile):
        if file.content_type != "application/gzip":
            raise InvalidFileFormat()

        # Get project
        proj = self.project_handler._get(proj_key)

        with TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Write the package file to temp dir
            tmp_pkg_file = tmp / "package.tgz"
            tmp_pkg_file.write_bytes(file.file.read())

            with tarfile.open(tmp_pkg_file) as tar_file:
                tar_file.extractall(tmp)

            pkg_info_file = tmp / "package/package.json"

            if not pkg_info_file.exists():
                raise PackageCorrupted()

            pkg_info = json.loads(pkg_info_file.read_text(encoding="utf-8"))

            # Create package directory below project directory
            pkg_dir = Path(proj.data_dir) / f"{pkg_info['name']}#{pkg_info['version']}"

            if pkg_dir.exists():
                raise PackageAlreadyExists()

            pkg_dir.mkdir()

            # Move package contents to package directory
            (tmp / "package").rename(pkg_dir / "package")

        pass
