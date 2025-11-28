import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

from fhir.resources.R4B.elementdefinition import ElementDefinition
from fhir.resources.R4B.structuredefinition import StructureDefinition
from pydantic import ValidationError

from ..fixed_value_extractor import FixedValueExtractor
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
    def resource_type(self) -> str | None:
        return getattr(self.__data, "type", None)

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

    @property
    def package_dir(self) -> Path | None:
        if self.__package is None:
            return None
        package_root = self.__package.dir
        candidate = package_root / "package"
        return candidate if candidate.is_dir() else package_root

    @property
    def package_id(self) -> str | None:
        return self.__package.id if self.__package is not None else None

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
    
    def _get_parent_path(self) -> str | None:
        """Get the parent path of this field."""
        if self.path is None or "." not in self.path:
            return None
        return self.path.rsplit(".", 1)[0]

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
    def types(self) -> list[str]:
        """Gibt die in den Element-Typen definierten code-Werte zurück."""
        type_codes: list[str] = []
        types = getattr(self.__data, "type", None) or []

        for t in types:
            code = getattr(t, "code", None)
            if code and code not in type_codes:
                type_codes.append(code)

        return type_codes
    
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
        return FixedValueExtractor.extract_pattern_coding_system(self.__data)
    
    @property
    def fixed_value(self) -> Any | None:
        """Extrahiert jeden fixed* Wert aus dem ElementDefinition.
        
        Returns:
            Der fixed value (beliebiger Typ) wenn vorhanden, None sonst
        """
        return FixedValueExtractor.extract_fixed_value(self.__data)
    
    @property
    def fixed_value_type(self) -> str | None:
        """Gibt den Typ des fixed value zurück (z.B. 'fixedUri', 'fixedString').
        
        Returns:
            Der Attributname des fixed value Typs wenn vorhanden, None sonst
        """
        return FixedValueExtractor.get_fixed_value_type(self.__data)
    
    @property
    def has_fixed_or_pattern(self) -> bool:
        """Prüft ob dieses Feld einen fixed oder pattern value hat.
        
        Returns:
            True wenn fixed oder pattern value vorhanden ist
        """
        return FixedValueExtractor.has_fixed_or_pattern_value(self.__data)
    
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

    def to_model(self, all_fields: Dict[str, "ProfileField"] | None = None) -> ProfileFieldModel:
        """Convert to ProfileFieldModel.
        
        Args:
            all_fields: Optional dictionary of all fields in the profile to check parent cardinality
            
        Returns:
            ProfileFieldModel with cardinality info and optional inherited note
        """
        cardinality_note = None
        min_val = self.min
        max_val = self.max
        
        # Check if parent has 0..0 cardinality
        if all_fields is not None:
            parent_path = self._get_parent_path()
            if parent_path:
                parent_field = all_fields.get(parent_path)
                if parent_field and parent_field.min == 0 and parent_field.max == "0":
                    # Inherit 0..0 from parent
                    min_val = 0
                    max_val = "0"
                    cardinality_note = f"inherited from {parent_path}"
        
        return ProfileFieldModel(
            min=min_val,
            max=max_val,
            must_support=self.must_support,
            types=self.types if len(self.types) else None,
            ref_types=self.ref_types if len(self.ref_types) else None,
            cardinality_note=cardinality_note,
        )
