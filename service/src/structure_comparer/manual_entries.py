import logging
from enum import StrEnum
from pathlib import Path

import yaml

from .errors import NotInitialized
from .manual_entries_migration import migrate_action_values, migrate_manual_entries
from .model.manual_entries import ManualEntries as ManualEntriesModel
from .model.manual_entries import ManualEntriesMapping as ManualEntriesMappingModel
from .model.manual_entries import ManualEntriesTargetCreation as ManualEntriesTargetCreationModel
from .model.manual_entries import ManualEntriesTransformation as ManualEntriesTransformationModel

logger = logging.getLogger(__name__)

yaml.SafeDumper.add_multi_representer(
    StrEnum,
    yaml.representer.SafeRepresenter.represent_str,
)


class ManualEntries:
    def __init__(self) -> None:
        self._data: ManualEntriesModel | None = None
        self._file: Path | None = None

    @property
    def entries(self) -> list[ManualEntriesMappingModel]:
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")

        return self._data.entries

    @property
    def transformation_entries(self) -> list[ManualEntriesTransformationModel]:
        """Get all transformation entries."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.transformation_entries

    @property
    def mapping_entries(self) -> list[ManualEntriesMappingModel]:
        """Get all mapping entries (new format)."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.mapping_entries

    def read(self, file: str | Path):
        self._file = Path(file)
        content = self._file.read_text(encoding="utf-8")

        suffix = self._file.suffix.lower()
        if suffix == ".json":
            # leere Datei -> leeres Objekt
            if not content.strip():
                self._data = ManualEntriesModel(entries=[])
            else:
                self._data = ManualEntriesModel.model_validate_json(content)
        elif suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)  # kann None sein
            if not isinstance(data, dict):
                data = {}
            
            # Apply migrations for legacy formats and action names
            data = migrate_manual_entries(data)  # Handles old format structure
            data = migrate_action_values(data)   # Migrates old action names
            
            # Mindestschema sicherstellen - support both old and new format
            if "entries" not in data or data["entries"] is None:
                data["entries"] = []
            if "mapping_entries" not in data or data["mapping_entries"] is None:
                data["mapping_entries"] = []
            if "transformation_entries" not in data or data["transformation_entries"] is None:
                data["transformation_entries"] = []
            # Phase 2.2: Support target_creation_entries
            if "target_creation_entries" not in data or data["target_creation_entries"] is None:
                data["target_creation_entries"] = []
            self._data = ManualEntriesModel.model_validate(data)
        else:
            # unbekanntes Format – defensiv: leeres Modell
            logger.warning("Unsupported manual entries file suffix '%s', defaulting to empty model", suffix)
            self._data = ManualEntriesModel(entries=[])

    def write(self):
        if self._file is None:
            raise NotInitialized("ManualEntries file was not set")

        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")

        # Drop auto-generated child entries – only persist manual decisions.
        for entry in self._data.entries:
            filtered_fields = []
            for field in entry.fields:
                field_payload = field.model_dump()
                if field_payload.pop("auto_generated", False):
                    # Skip auto-generated helper entries entirely
                    continue
                # Keep inherited_from for manually applied children (auto_generated=False)
                # but remove it if it was auto-generated
                filtered_fields.append(field.__class__.model_validate(field_payload))
            entry.fields = filtered_fields

        # Also filter mapping_entries
        for entry in self._data.mapping_entries:
            filtered_fields = []
            for field in entry.fields:
                field_payload = field.model_dump()
                if field_payload.pop("auto_generated", False):
                    continue
                field_payload.pop("inherited_from", None)
                filtered_fields.append(field.__class__.model_validate(field_payload))
            entry.fields = filtered_fields

        # Prepare output data - preserve null values for backwards compatibility!
        output_data = self._data.model_dump()

        # Remove empty new-format lists if we're using legacy format
        if not self._data.mapping_entries:
            output_data.pop("mapping_entries", None)
        if not self._data.transformation_entries:
            output_data.pop("transformation_entries", None)
        # Phase 2.2: Handle target_creation_entries in output
        if not self._data.target_creation_entries:
            output_data.pop("target_creation_entries", None)
        # Remove empty legacy entries only if using new format
        has_new_format_entries = (
            self._data.mapping_entries or
            self._data.transformation_entries or
            self._data.target_creation_entries
        )
        if has_new_format_entries and not self._data.entries:
            output_data.pop("entries", None)

        content = None
        if self._file.suffix == ".json":
            content = self._data.model_dump_json(indent=4)
        elif self._file.suffix == ".yaml":
            content = yaml.safe_dump(output_data, default_flow_style=False, allow_unicode=True)

        if content is not None:
            self._file.write_text(content, encoding="utf-8")

    def __iter__(self):
        return iter(self.entries)

    def get(self, key, default=None) -> ManualEntriesMappingModel | None:
        """Get a mapping entry by ID (from legacy entries)."""
        return next((e for e in self.entries if e.id == key), default)

    def get_transformation(self, key) -> ManualEntriesTransformationModel | None:
        """Get a transformation entry by ID."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.get_transformation(key)

    def set_transformation(self, transformation: ManualEntriesTransformationModel) -> None:
        """Add or update a transformation entry."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        self._data.set_transformation(transformation)

    def remove_transformation(self, transformation_id: str) -> bool:
        """Remove a transformation entry."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.remove_transformation(transformation_id)

    # === TARGET CREATION METHODS ===
    # Phase 2, Step 2.2: Manual Entries erweitern ✅
    # Created: 2025-12-03

    @property
    def target_creation_entries(self) -> list[ManualEntriesTargetCreationModel]:
        """Get all target creation entries."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.target_creation_entries

    def get_target_creation(self, key) -> ManualEntriesTargetCreationModel | None:
        """Get a target creation entry by ID."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.get_target_creation(key)

    def set_target_creation(self, target_creation: ManualEntriesTargetCreationModel) -> None:
        """Add or update a target creation entry."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        self._data.set_target_creation(target_creation)

    def remove_target_creation(self, target_creation_id: str) -> bool:
        """Remove a target creation entry."""
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")
        return self._data.remove_target_creation(target_creation_id)

    def __getitem__(self, key) -> ManualEntriesMappingModel:
        return next((e for e in self.entries if e.id == key))

    def __setitem__(self, key, value) -> None:
        i = next((i for i, e in enumerate(self.entries) if e.id == key), None)

        if i is None:
            self.entries.append(value)

        else:
            self.entries[i] = value
