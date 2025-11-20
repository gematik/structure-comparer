import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
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
        self.__fields: Dict[str, "ProfileField"] = None
        self.__init_fields()
        self.__package = package

    @staticmethod
    def _sanitize_structure_definition(sd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ergänzt fehlende 'base.min'/'base.max'/'base.path' in snapshot.element[*].
        Fallback-Reihenfolge:
          1) base.min/base.max aus Elementfeldern 'min'/'max' übernehmen (falls vorhanden)
          2) andernfalls Defaults setzen: min=0, max="*"
        'base.path' wird aus 'element.path' oder ersatzweise aus 'element.id' (bis ':') abgeleitet.
        """
        try:
            elements = sd.get("snapshot", {}).get("element", [])
            for el in elements:
                base = el.get("base")
                # Pfad ableiten: bevorzugt 'path', notfalls aus 'id' bis zum ersten ':' bzw. ganz
                path_val: Optional[str] = el.get("path")
                if not path_val:
                    el_id = el.get("id")
                    if isinstance(el_id, str):
                        path_val = el_id.split(":", 1)[0]

                # Sicherstellen, dass base existiert
                if base is None:
                    base = {}
                    el["base"] = base

                # min aus Element übernehmen oder Default 0
                if base.get("min") is None:
                    el_min = el.get("min")
                    base["min"] = int(el_min) if el_min is not None else 0

                # max aus Element übernehmen oder Default "*"
                if base.get("max") is None:
                    el_max = el.get("max")
                    # Im SD ist 'max' ein String (z. B. "1" oder "*")
                    base["max"] = str(el_max) if el_max is not None else "*"
 
                # path setzen, falls fehlt
                if base.get("path") is None and path_val is not None:
                    base["path"] = path_val
        except Exception:
            # Im Fehlerfall nichts kaputtvalidieren; lieber unverändert zurückgeben
            logger.exception("Failed to sanitize StructureDefinition")
        return sd

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
            raw = json.loads(path.read_text(encoding="utf-8"))
            # VOR der Validierung sanitizen
            sanitized = Profile._sanitize_structure_definition(raw)
            return Profile(data=sanitized, package=package)

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

    @property
    def webUrl(self) -> str | None:
        """Get the web URL (Simplifier/documentation link) if set."""
        return getattr(self, '_web_url', None)

    @property
    def package(self) -> str | None:
        """Get the package name if set."""
        return getattr(self, '_package_name', None)

    def set_metadata(self, web_url: str | None = None, package_name: str | None = None) -> None:
        """Set additional metadata like webUrl and package name."""
        if web_url:
            self._web_url = web_url
        if package_name:
            self._package_name = package_name

    def __lt__(self, other: "Profile") -> bool:
        return self.key < other.key

    def __to_dict(self) -> dict:
        result = {
            "id": self.id,
            "url": self.url,
            "key": self.key,
            "name": self.name,
            "version": self.version,
        }
        # Add optional fields if they exist
        if hasattr(self, '_web_url') and self._web_url:
            result["webUrl"] = self._web_url
        if hasattr(self, '_package_name') and self._package_name:
            result["package"] = self._package_name
        return result

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
        """Gibt die in den Element-Typen erlaubten targetProfile (References) zurück."""
        refs: list[str] = []
        types = getattr(self.__data, "type", None) or []

        for t in types:
            if getattr(t, "code", None) != "Reference":
                continue
            target_profiles = getattr(t, "targetProfile", None) or []
            for p in target_profiles:
                if p and p not in refs:
                    refs.append(p)

        return refs
    
    @property
    def pattern_coding_system(self) -> str | None:
        """Extrahiert das system aus patternCoding, falls vorhanden."""
        pattern_coding = getattr(self.__data, "patternCoding", None)
        if pattern_coding is None:
            return None
        return getattr(pattern_coding, "system", None)
    
    @property
    def is_default(self) -> bool:
        # defensiv prüfen, da manche SDs unvollständige base liefern können
        base = getattr(self.__data, "base", None)
        if not base:
            return False
        try:
            base_min = getattr(base, "min", None)
            base_max = getattr(base, "max", None)
            return (
                (base_min is not None)
                and (base_max is not None)
                and (self.min == base_min)
                and (self.max == base_max)
            )
        except Exception:
            return False

    def to_model(self) -> ProfileFieldModel:
        return ProfileFieldModel(
            min=self.min,
            max=self.max,
            must_support=self.must_support,
            ref_types=self.ref_types if len(self.ref_types) else None,
        )
