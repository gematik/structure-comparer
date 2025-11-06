import logging
from enum import StrEnum
from pathlib import Path
from typing import Iterator

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

    def read(self, file: str | Path) -> None:
        self._file = Path(file)
        content = self._file.read_text(encoding="utf-8").strip()

        if not content:
            logger.warning(
                f"ManualEntries file {self._file} is empty. Using default model."
            )
            self._data = ManualEntriesModel(entries=[])
            return

        try:
            if self._file.suffix == ".json":
                self._data = ManualEntriesModel.model_validate_json(content)
            elif self._file.suffix == ".yaml":
                parsed = yaml.safe_load(content) or {}
                self._data = ManualEntriesModel.model_validate(parsed)
            else:
                raise ValueError(f"Unsupported file extension: {self._file.suffix}")
        except Exception as e:
            logger.exception(f"Failed to read manual entries from {self._file}: {e}")
            raise

    def write(self) -> None:
        if self._file is None:
            raise NotInitialized("ManualEntries file was not set")
        if self._data is None:
            raise NotInitialized("ManualEntries data was not initialized")

        content: str | None = None
        if self._file.suffix == ".json":
            content = self._data.model_dump_json(indent=4)
        elif self._file.suffix == ".yaml":
            content = yaml.safe_dump(self._data.model_dump())
        else:
            raise ValueError(f"Unsupported file extension: {self._file.suffix}")

        self._file.write_text(content, encoding="utf-8")

    def __iter__(self) -> Iterator[ManualEntriesMappingModel]:
        return iter(self.entries)

    def get(self, key: str, default=None) -> ManualEntriesMappingModel | None:
        return next((e for e in self.entries if e.id == key), default)

    def __getitem__(self, key: str) -> ManualEntriesMappingModel:
        for entry in self.entries:
            if entry.id == key:
                return entry
        raise KeyError(f"No entry found with ID: {key}")

    def __setitem__(self, key: str, value: ManualEntriesMappingModel) -> None:
        for i, entry in enumerate(self.entries):
            if entry.id == key:
                self.entries[i] = value
                return
        self.entries.append(value)
