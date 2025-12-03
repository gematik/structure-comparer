from pydantic import BaseModel

from .mapping import MappingFieldBase
from .target_creation import TargetCreationFieldBase
from .transformation import TransformationFieldBase


class ManualEntriesMapping(BaseModel):
    """Manual entries for a Mapping (profile-to-profile level)."""
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

    def __contains__(self, key) -> bool:
        return any(f.name == key for f in self.fields)


class ManualEntriesTransformation(BaseModel):
    """Manual entries for a Transformation (bundle-to-structure level).

    Transformation fields use action='transform' and reference child Mappings via 'map'.
    """
    id: str
    fields: list[TransformationFieldBase] = []

    def get(self, key, default=None) -> TransformationFieldBase | None:
        return next((f for f in self.fields if f.name == key), default)

    def get_field(self, name: str) -> TransformationFieldBase | None:
        """Get a field by name."""
        return next((f for f in self.fields if f.name == name), None)

    def set_field(self, field: TransformationFieldBase) -> None:
        """Set or update a field."""
        i = next((i for i, f in enumerate(self.fields) if f.name == field.name), None)
        if i is not None:
            self.fields[i] = field
        else:
            self.fields.append(field)

    def remove_field(self, name: str) -> bool:
        """Remove a field by name. Returns True if removed."""
        i = next((i for i, f in enumerate(self.fields) if f.name == name), None)
        if i is not None:
            del self.fields[i]
            return True
        return False

    def __getitem__(self, key) -> TransformationFieldBase:
        field = next((f for f in self.fields if f.name == key), None)
        if field is None:
            raise KeyError(key)
        return field

    def __setitem__(self, key, value) -> None:
        i = next((i for i, field in enumerate(self.fields) if field.name == key), None)
        if i is not None:
            self.fields[i] = value
        else:
            self.fields.append(value)

    def __delitem__(self, key):
        del_i = next((i for i, f in enumerate(self.fields) if f.name == key), None)
        if del_i is not None:
            del self.fields[del_i]

    def __contains__(self, key) -> bool:
        return any(f.name == key for f in self.fields)


class ManualEntriesTargetCreation(BaseModel):
    """Manual entries for a Target Creation (target-only profile definition).

    Target Creation fields only support 'manual' and 'fixed' actions.
    No 'other' field since copy_from/copy_to is not allowed.
    """
    id: str
    fields: list[TargetCreationFieldBase] = []

    def get(self, key, default=None) -> TargetCreationFieldBase | None:
        return next((f for f in self.fields if f.name == key), default)

    def get_field(self, name: str) -> TargetCreationFieldBase | None:
        """Get a field by name."""
        return next((f for f in self.fields if f.name == name), None)

    def set_field(self, field: TargetCreationFieldBase) -> None:
        """Set or update a field."""
        i = next((i for i, f in enumerate(self.fields) if f.name == field.name), None)
        if i is not None:
            self.fields[i] = field
        else:
            self.fields.append(field)

    def remove_field(self, name: str) -> bool:
        """Remove a field by name. Returns True if removed."""
        i = next((i for i, f in enumerate(self.fields) if f.name == name), None)
        if i is not None:
            del self.fields[i]
            return True
        return False

    def __getitem__(self, key) -> TargetCreationFieldBase:
        field = next((f for f in self.fields if f.name == key), None)
        if field is None:
            raise KeyError(key)
        return field

    def __setitem__(self, key, value) -> None:
        i = next((i for i, field in enumerate(self.fields) if field.name == key), None)
        if i is not None:
            self.fields[i] = value
        else:
            self.fields.append(value)

    def __delitem__(self, key):
        del_i = next((i for i, f in enumerate(self.fields) if f.name == key), None)
        if del_i is not None:
            del self.fields[del_i]

    def __contains__(self, key) -> bool:
        return any(f.name == key for f in self.fields)


class ManualEntries(BaseModel):
    """Container for all manual entries in a project.

    Supports legacy format (entries) and new format with explicit separation:
    mapping_entries, transformation_entries, and target_creation_entries.
    """
    # Legacy format - kept for backwards compatibility
    entries: list[ManualEntriesMapping] = []

    # New format - explicit separation
    mapping_entries: list[ManualEntriesMapping] = []
    transformation_entries: list[ManualEntriesTransformation] = []
    target_creation_entries: list[ManualEntriesTargetCreation] = []

    @property
    def all_mapping_entries(self) -> list[ManualEntriesMapping]:
        """Returns all mapping entries, combining legacy and new format."""
        # Combine and deduplicate by id
        seen_ids = set()
        result = []
        for entry in self.mapping_entries + self.entries:
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                result.append(entry)
        return result

    def get_transformation(self, transformation_id: str) -> ManualEntriesTransformation | None:
        """Get manual entries for a specific transformation."""
        return next(
            (t for t in self.transformation_entries if t.id == transformation_id),
            None
        )

    def set_transformation(self, transformation: ManualEntriesTransformation) -> None:
        """Add or update a transformation entry."""
        i = next(
            (i for i, t in enumerate(self.transformation_entries) if t.id == transformation.id),
            None
        )
        if i is not None:
            self.transformation_entries[i] = transformation
        else:
            self.transformation_entries.append(transformation)

    def remove_transformation(self, transformation_id: str) -> bool:
        """Remove a transformation entry. Returns True if removed."""
        i = next(
            (i for i, t in enumerate(self.transformation_entries) if t.id == transformation_id),
            None
        )
        if i is not None:
            del self.transformation_entries[i]
            return True
        return False

    # Target Creation methods
    def get_target_creation(self, target_creation_id: str) -> ManualEntriesTargetCreation | None:
        """Get manual entries for a specific target creation."""
        return next(
            (tc for tc in self.target_creation_entries if tc.id == target_creation_id),
            None
        )

    def set_target_creation(self, target_creation: ManualEntriesTargetCreation) -> None:
        """Add or update a target creation entry."""
        i = next(
            (i for i, tc in enumerate(self.target_creation_entries)
             if tc.id == target_creation.id),
            None
        )
        if i is not None:
            self.target_creation_entries[i] = target_creation
        else:
            self.target_creation_entries.append(target_creation)

    def remove_target_creation(self, target_creation_id: str) -> bool:
        """Remove a target creation entry. Returns True if removed."""
        i = next(
            (i for i, tc in enumerate(self.target_creation_entries)
             if tc.id == target_creation_id),
            None
        )
        if i is not None:
            del self.target_creation_entries[i]
            return True
        return False
