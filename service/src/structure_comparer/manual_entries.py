import logging
from enum import StrEnum
from pathlib import Path

import yaml

from .errors import NotInitialized
from .model.manual_entries import ManualEntries as ManualEntriesModel
from .model.manual_entries import ManualEntriesMapping as ManualEntriesMappingModel

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
            # Mindestschema sicherstellen
            if "entries" not in data or data["entries"] is None:
                data["entries"] = []
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

        logger.debug(f"write() called for file: {self._file}")
        logger.debug(f"Number of entries before filtering: {len(self._data.entries)}")
        for i, entry in enumerate(self._data.entries):
            logger.debug(
                f"  Entry {i}: id={entry.id}, "
                f"num_fields={len(entry.fields)}"
            )

        # Drop auto-generated child entries – only persist manual decisions.
        for entry in self._data.entries:
            filtered_fields = []
            for field in entry.fields:
                field_payload = field.model_dump()
                if field_payload.pop("auto_generated", False):
                    # Skip auto-generated helper entries entirely
                    continue
                field_payload.pop("inherited_from", None)
                filtered_fields.append(field.__class__.model_validate(field_payload))
            entry.fields = filtered_fields

        logger.debug(f"Number of entries after filtering: {len(self._data.entries)}")
        for i, entry in enumerate(self._data.entries):
            logger.debug(
                f"  Entry {i} after filter: id={entry.id}, "
                f"num_fields={len(entry.fields)}"
            )

        content = None
        if self._file.suffix == ".json":
            content = self._data.model_dump_json(indent=4)
        elif self._file.suffix == ".yaml":
            content = yaml.safe_dump(self._data.model_dump())

        if content is not None:
            logger.debug(f"Writing content to {self._file}")
            logger.debug(f"Content preview: {content[:500]}")
            self._file.write_text(content, encoding="utf-8")
            logger.debug("Write completed successfully")

    def __iter__(self):
        return iter(self.entries)

    def get(self, key, default=None) -> ManualEntriesMappingModel | None:
        return next((e for e in self.entries if e.id == key), default)

    def __getitem__(self, key) -> ManualEntriesMappingModel:
        return next((e for e in self.entries if e.id == key))

    def __setitem__(self, key, value) -> None:
        i = next((i for i, e in enumerate(self.entries) if e.id == key), None)

        if i is None:
            self.entries.append(value)

        else:
            self.entries[i] = value
