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
        # Try to find the index of the field
        i = next((i for i, field in enumerate(self.fields) if field.name == key), None)

        # Replace the field if found
        if i is not None:
            self.fields[i] = value

        # Otherwise, append a new field
        else:
            self.fields.append(value)


class ManualEntries(BaseModel):
    entries: list[ManualEntriesMapping]
