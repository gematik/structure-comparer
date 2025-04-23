from pydantic import BaseModel

from .mapping import MappingFieldBase


class ManualEntriesMapping(BaseModel):
    id: str
    fields: list[MappingFieldBase]

    def get(self, key, default=None) -> MappingFieldBase:
        return next((f for f in self.fields if f.name == key), default)

    def __getitem__(self, key) -> MappingFieldBase:
        return next((f for f in self.fields if f.name == key))

    def __setitem__(self, key, value) -> None:
        i = next(i for i in enumerate(self.fields) if self.fields[i].name == key)
        self.fields[i] = value


class ManualEntries(BaseModel):
    entries: list[ManualEntriesMapping]
