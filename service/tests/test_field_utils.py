"""Tests for field utility functions."""

from structure_comparer.recommendations.field_utils import (
    are_types_compatible,
    get_field_types,
)


class FieldWithTypes:
    """Mock field object with types."""
    
    def __init__(self, types=None):
        self.types = types


class FieldWithoutTypes:
    """Mock field object without types attribute."""
    
    def __init__(self):
        pass


def test_get_field_types_with_types():
    """Test getting types from a field that has types."""
    field = FieldWithTypes(types=["string", "code"])
    
    result = get_field_types(field)
    
    assert result == ["string", "code"]


def test_get_field_types_with_none_types():
    """Test getting types from a field that has types=None."""
    field = FieldWithTypes(types=None)
    
    result = get_field_types(field)
    
    assert result == []


def test_get_field_types_without_types_attribute():
    """Test getting types from a field without types attribute."""
    field = FieldWithoutTypes()
    
    result = get_field_types(field)
    
    assert result == []


def test_get_field_types_with_none_field():
    """Test getting types from None field."""
    result = get_field_types(None)
    
    assert result == []


def test_are_types_compatible_same_type():
    """Test compatibility check with same types."""
    source = FieldWithTypes(types=["CodeableConcept"])
    target = FieldWithTypes(types=["CodeableConcept"])
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is True
    assert warning is None


def test_are_types_compatible_overlapping_types():
    """Test compatibility check with overlapping types."""
    source = FieldWithTypes(types=["string", "code"])
    target = FieldWithTypes(types=["code", "uri"])
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is True
    assert warning is None


def test_are_types_compatible_incompatible_types():
    """Test compatibility check with incompatible types."""
    source = FieldWithTypes(types=["string"])
    target = FieldWithTypes(types=["CodeableConcept"])
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is False
    assert warning is not None
    assert "string" in warning
    assert "CodeableConcept" in warning
    assert "type mismatch" in warning.lower()


def test_are_types_compatible_both_no_types():
    """Test compatibility check when both fields have no types."""
    source = FieldWithTypes(types=None)
    target = FieldWithTypes(types=None)
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is True
    assert warning is None


def test_are_types_compatible_source_no_types():
    """Test compatibility check when source has no types."""
    source = FieldWithTypes(types=None)
    target = FieldWithTypes(types=["string"])
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is True
    assert warning is not None
    assert "Source field has no type information" in warning


def test_are_types_compatible_target_no_types():
    """Test compatibility check when target has no types."""
    source = FieldWithTypes(types=["string"])
    target = FieldWithTypes(types=None)
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is True
    assert warning is not None
    assert "Target field has no type information" in warning


def test_are_types_compatible_multiple_incompatible():
    """Test compatibility check with multiple incompatible types."""
    source = FieldWithTypes(types=["string", "code"])
    target = FieldWithTypes(types=["CodeableConcept", "Coding"])
    
    is_compatible, warning = are_types_compatible(source, target)
    
    assert is_compatible is False
    assert warning is not None
    assert "string, code" in warning or "code, string" in warning
    assert "CodeableConcept" in warning
    assert "Coding" in warning
