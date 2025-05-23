import json
from pathlib import Path

from ..errors import NotAllowed
from ..model.package import Package as PackageModel
from ..model.package import PackageInfo
from .config import PackageConfig
from .profile import Profile


class Package:
    def __init__(
        self,
        dir: Path,
        parent,
        config: PackageConfig | None = None,
    ):
        self.dir = dir
        self.config = config
        self.info: PackageInfo | None = None
        self.profiles: list[Profile]
        self.__parent = parent

        if (info_file := self.dir / "package/package.json").exists():
            self.info = PackageInfo.model_validate_json(
                info_file.read_text(encoding="utf-8")
            )

        self.__load_profiles()

    @property
    def name(self) -> str | None:
        if self.info is not None:
            return self.info.name

        elif self.config is not None:
            return self.config.name

        return None

    @property
    def version(self) -> str | None:
        if self.info is not None:
            return self.info.version

        elif self.config is not None:
            return self.config.version

        return None

    @property
    def id(self) -> str:
        return f"{self.name}#{self.version}"

    @property
    def display(self) -> str | None:
        if self.info is not None and self.info.title is not None:
            return self.info.title

        if self.info is not None and self.info.description is not None:
            return self.info.description

        elif self.config is not None:
            return self.config.display

        return None

    @display.setter
    def display(self, value) -> None:
        if self.info is not None:
            raise NotAllowed()

        elif self.config is not None:
            self.config.display = value
            self.write_config()

    def write_config(self):
        self.__parent.write_config()

    def __load_profiles(self) -> None:
        self.profiles = [
            Profile.from_json(file, self)
            for file in (self.dir).glob("**/*.json")
            if _is_profile_file(file)
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


def _is_profile_file(file: Path) -> bool:
    if not file.is_file():
        return False

    content = None
    try:
        content = json.loads(file.read_text(encoding="utf-8"))

    except json.JSONDecodeError:
        return False

    return content.get("resourceType") == "StructureDefinition"
