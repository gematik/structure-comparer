import json
from pathlib import Path

from ..errors import NotAllowed
from ..model.package import Package as PackageModel
from ..model.package import PackageWithStatus as PackageWithStatusModel
from ..model.package import PackageStatus
from ..model.package import PackageInfo
from .config import PackageConfig
from .profile import Profile


class Package:
    def __init__(
        self,
        dir: Path,
        parent,
        config: PackageConfig | None = None,
        status: PackageStatus = PackageStatus.AVAILABLE,
    ):
        self.dir = dir
        self.config = config
        self.info: PackageInfo | None = None
        self.profiles: list[Profile]
        self.__parent = parent
        self._status = status

        if (info_file := self.dir / "package/package.json").exists():
            self.info = PackageInfo.model_validate_json(
                info_file.read_text(encoding="utf-8")
            )

        # Only load profiles if package is actually available on disk
        if self._status == PackageStatus.AVAILABLE:
            self.__load_profiles()
        else:
            self.profiles = []

    @classmethod
    def from_config_only(cls, config: PackageConfig, parent) -> "Package":
        """
        Create a Package instance from config only (for missing packages).
        The package is not downloaded yet, so no directory exists.
        """
        # Create a dummy path that doesn't exist
        dummy_dir = parent.data_dir / f"{config.name}#{config.version}"
        instance = cls.__new__(cls)
        instance.dir = dummy_dir
        instance.config = config
        instance.info = None
        instance.profiles = []
        instance._Package__parent = parent
        instance._status = PackageStatus.MISSING
        return instance

    @property
    def status(self) -> PackageStatus:
        return self._status

    @property
    def is_available(self) -> bool:
        """Check if package files are actually present on disk."""
        return self._status == PackageStatus.AVAILABLE

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
        profiles = []
        for file in (self.dir).glob("**/*.json"):
            if _is_profile_file(file):
                p = Profile.from_json(file, self)
                if p is not None:
                    profiles.append(p)
        self.profiles = profiles

    def to_model(self) -> PackageModel:

        definition = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "status": self._status,
        }

        if self.display:
            definition["display"] = self.display

        # Add optional metadata from info if available
        if self.info:
            if self.info.description:
                definition["description"] = self.info.description
            if self.info.canonical:
                definition["canonical"] = self.info.canonical

        return PackageModel(**definition)

    def to_model_with_status(self) -> PackageWithStatusModel:
        """Return package model with status information."""
        definition = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "status": self._status,
        }

        if self.display:
            definition["display"] = self.display

        # Add optional metadata from info if available
        if self.info:
            if self.info.description:
                definition["description"] = self.info.description
            if self.info.canonical:
                definition["canonical"] = self.info.canonical

        return PackageWithStatusModel(**definition)

    @property
    def key(self) -> str:
        """Return the package key (name#version)."""
        return f"{self.name}#{self.version}"


def _is_profile_file(file: Path) -> bool:
    if not file.is_file():
        return False

    content = None
    try:
        content = json.loads(file.read_text(encoding="utf-8"))

    except json.JSONDecodeError:
        return False

    return content.get("resourceType") == "StructureDefinition"
