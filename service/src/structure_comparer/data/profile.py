import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fhir.resources.R4B.elementdefinition import ElementDefinition
from fhir.resources.R4B.structuredefinition import StructureDefinition
from pydantic import ValidationError

from ..model.profile import PackageProfile as PackageProfileModel
from ..model.profile import Profile as ProfileModel
from ..model.profile import ProfileField as ProfileFieldModel

logger = logging.getLogger(__name__)


class Profile:
    def __init__(self, data: dict, package=None) -> None:
        self.__data = StructureDefinition.model_validate(data)
        self.__fields: Dict[str, ProfileField] = {}
        self.__init_fields()
        self.__package = package

    def __init_fields(self) -> None:
        for elem in self.__data.snapshot.element:
            field = ProfileField(elem)
            if field.path:
                self.__fields[field.id] = field

    def __str__(self) -> str:
        return f"(name={self.name}, version={self.version}, fields={list(self.fields)})"

    def __repr__(self) -> str:
        return str(self)

    @staticmethod
    def from_json(path: Path, package=None) -> "Profile":
        if not path.exists():
            raise FileNotFoundError(
                f"The file {path} does not exist. Please check the path and try again."
            )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Profile(data=data, package=package)
        except Exception as e:
            logger.error("Failed to read profile from '%s'", path)
            logger.exception(e)
            raise

    @property
    def name(self) -> str:
        return self.__data.name

    @property
    def version(self) -> str:
        return self.__data.version

    @property
    def fields(self) -> Dict[str, "ProfileField"]:
        return self.__fields

    @property
    def key(self) -> str:
        return f"{self.url}|{self.version}"

    @property
    def id(self) -> str:
        return self.__data.id

    @property
    def url(self) -> str:
        return self.__data.url

    def __lt__(self, other: "Profile") -> bool:
        return self.key < other.key

    def _to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "key": self.key,
            "name": self.name,
            "version": self.version,
        }

    def _to_pkg_dict(self) -> dict:
        d = self._to_dict()
        d["package"] = self.__package.id if self.__package else None
        return d

    def to_model(self) -> Optional[ProfileModel]:
        try:
            return ProfileModel(**self._to_dict())
        except ValidationError as e:
            logger.exception("Failed to convert Profile to ProfileModel: %s", e)
            return None

    def to_pkg_model(self) -> Optional[PackageProfileModel]:
        try:
            return PackageProfileModel(**self._to_pkg_dict())
        except ValidationError as e:
            logger.exception("Failed to convert Profile to PackageProfileModel: %s", e)
            return None


class ProfileField:
    def __init__(self, data: ElementDefinition) -> None:
        self.__data = data
        self.__id = str(uuid4())

    def __str__(self) -> str:
        return f"(name={self.name}, id={self.id}, min={self.min}, max={self.max})"

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, value: object) -> bool:
        return (
            isinstance(value, ProfileField)
            and self.min == value.min
            and self.max == value.max
        )

    @property
    def id(self) -> str:
        return self.__id

    @property
    def path_full(self) -> str:
        return self.__data.id

    @property
    def path(self) -> Optional[str]:
        return "." + self.path_full.split(".", 1)[1] if "." in self.path_full else None

    @property
    def min(self) -> int:
        return self.__data.min

    @property
    def max(self) -> str:
        return self.__data.max

    @property
    def max_num(self) -> float:
        return float("inf") if self.max == "*" else int(self.max)

    @property
    def must_support(self) -> bool:
        return bool(self.__data.mustSupport)

    @property
    def ref_types(self) -> List[str]:
        if not self.__data.type:
            return []
        return [
            p
            for t in self.__data.type
            if t.code == "Reference" and t.targetProfile
            for p in t.targetProfile
        ]

    @property
    def is_default(self) -> bool:
        return self.__data.base == self

    def to_model(self) -> ProfileFieldModel:
        ref_types = self.ref_types
        return ProfileFieldModel(
            min=self.min,
            max=self.max,
            must_support=self.must_support,
            ref_types=ref_types if ref_types else None,
        )
