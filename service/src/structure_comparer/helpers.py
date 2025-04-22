from .data.mapping import Mapping, MappingField


def get_field_by_name(mapping: Mapping, field_name: str) -> MappingField:
    for field in mapping.fields.values():
        if field.name == field_name:
            return field
    return None
