import json
import logging
from pathlib import Path
from typing import Dict, List
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
        self.__fields: List[str, ProfileField] = None
        self.__init_fields()
        self.__package = package

    def __str__(self) -> str:
        return f"(name={self.name}, version={self.version}, fields={self.fields})"

    def __repr__(self) -> str:
        return str(self)

    def __init_fields(self) -> None:
        self.__fields: Dict[str, ProfileField] = {}
        for elem in self.__data.snapshot.element:
            field = ProfileField(elem)
            if field.path is not None:
                self.__fields[field.id] = field

    @staticmethod
    def from_json(path: Path, package=None) -> "Profile":
        if not path.exists():
            raise FileNotFoundError(
                f"The file {path} does not exist. Please check the file path and try again."
            )

        try:
            return Profile(
                data=json.loads(path.read_text(encoding="utf-8")), package=package
            )

        except Exception as e:
            logger.error("failed to read file '%s'", str(path))
            logger.exception(e)

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

    def __to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "key": self.key,
            "name": self.name,
            "version": self.version,
        }

    def __to_pkg_dict(self) -> dict:
        dict_ = self.__to_dict()
        dict_["package"] = self.__package.id

        return dict_

    def to_model(self) -> ProfileModel:
        try:
            model = ProfileModel(**self.__to_dict())
        except ValidationError as e:
            logger.exception(e)

        else:
            return model

    def to_pkg_model(self) -> ProfileModel:
        try:
            model = PackageProfileModel(**self.__to_pkg_dict())
        except ValidationError as e:
            logger.exception(e)

        else:
            return model


class ProfileField:
    def __init__(
        self,
        data: ElementDefinition,
    ) -> None:
        self.__data = data
        self.__id = str(uuid4())

    def __str__(self) -> str:
        return f"(name={self.name}, id={self.id}, min={self.min}, max={self.max})"

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, value: object) -> bool:
        return self.min == value.min and self.max == value.max

    @property
    def id(self) -> str:
        return self.__id

    @property
    def path_full(self) -> str:
        return self.__data.id

    @property
    def path(self) -> str:
        return (
            ("." + self.path_full.split(".", 1)[1]) if "." in self.path_full else None
        )

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
        return self.__data.mustSupport if self.__data.mustSupport else False

    @property
    def ref_types(self) -> list[str]:
        return (
            [
                p
                for t in self.__data.type
                if t.code == "Reference"
                for p in t.targetProfile
            ]
            if self.__data.type is not None
            else []
        )

    @property
    def is_default(self) -> bool:
        return self == self.__data.base

    def to_model(self) -> ProfileFieldModel:
        return ProfileFieldModel(
            min=self.min,
            max=self.max,
            must_support=self.must_support,
            ref_types=self.ref_types if len(self.ref_types) else None,
        )
