from pathlib import Path

from ..model.package import Package as PackageModel
from .config import PackageConfig
from .profile import Profile


class Package:
    def __init__(self, data_dir: Path, config: PackageConfig, parent):
        self.data_dir = data_dir
        self.config = config
        self.profiles: list[Profile] = None
        self.__parent = parent
        self.__load_profiles()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def version(self) -> str | None:
        return self.config.version

    @property
    def id(self) -> str:
        return f"{self.name}#{self.version}"

    @property
    def display(self) -> str:
        return self.config.display

    @display.setter
    def display(self, value) -> None:
        self.config.display = value
        self.write_config()

    def write_config(self):
        self.__parent.write_config()

    def __load_profiles(self) -> None:
        self.profiles = [
            Profile.from_json(file, self)
            for file in (self.data_dir / self.id).iterdir()
            if file.is_file()
        ]

    def to_model(self) -> PackageModel:

        definition = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
        }

        if self.display:
            definition["display"] = self.display

        return PackageModel(**definition)
