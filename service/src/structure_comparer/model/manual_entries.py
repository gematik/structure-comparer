from pydantic import BaseModel

from .mapping import MappingFieldBase


class ManualEntriesMapping(BaseModel):
    id: str
    fields: list[MappingFieldBase] = []

    def get(self, key, default=None) -> MappingFieldBase | None:
        return next((f for f in self.fields if f.name == key), default)

    def __getitem__(self, key) -> MappingFieldBase:
        field = next((f for f in self.fields if f.name == key), None)
        if field is None:
            raise KeyError(key)
        return field

    def __setitem__(self, key, value) -> None:
        # Try to find the index of the field
        i = next((i for i, field in enumerate(self.fields) if field.name == key), None)

        # Replace the field if found
        if i is not None:
            self.fields[i] = value

        # Otherwise, append a new field
        else:
            self.fields.append(value)

    def __delitem__(self, key):
        del_i = next((i for i, f in enumerate(self.fields) if f.name == key), None)
        if del_i is not None:
            del self.fields[del_i]


class ManualEntries(BaseModel):
    entries: list[ManualEntriesMapping]
