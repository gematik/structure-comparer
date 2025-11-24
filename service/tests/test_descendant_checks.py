"""Tests for descendant checking helper functions in field_hierarchy_analyzer."""

from typing import Dict

from structure_comparer.field_hierarchy.field_hierarchy_analyzer import (
    all_descendants_compatible,
    all_descendants_compatible_or_solved,
)
from structure_comparer.model.mapping_action_models import (
    EvaluationResult,
    EvaluationStatus,
    MappingStatus,
)


class StubField:
    """Stub field for testing with classification attribute."""

    def __init__(self, name: str, classification: str = "compatible"):
        self.name = name
        self.classification = classification


def create_mapping(field_defs) -> Dict[str, StubField]:
    """
    Create a mapping dictionary from field definitions.

    Args:
        field_defs: List of tuples (name, classification) or just names (defaults to "compatible")

    Returns:
        Dictionary mapping field names to StubField objects
    """
    fields: Dict[str, StubField] = {}
    for definition in field_defs:
        if isinstance(definition, tuple):
            name, classification = definition
        else:
            name, classification = definition, "compatible"
        fields[name] = StubField(name, classification)
    return fields


# Tests for all_descendants_compatible


def test_all_descendants_compatible_returns_true_for_field_without_children():
    """Fall A: Root field without children should return True."""
    mapping = create_mapping([
        "Patient",
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is True


def test_all_descendants_compatible_returns_true_when_all_descendants_are_compatible():
    """Fall B: Root field with multiple descendants, all compatible."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.name.family", "compatible"),
        ("Patient.name.given", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is True


def test_all_descendants_compatible_returns_false_when_one_descendant_is_warning():
    """Fall C: At least one descendant with warning classification."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.name.family", "warning"),
        ("Patient.birthDate", "compatible"),
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is False


def test_all_descendants_compatible_returns_false_when_one_descendant_is_incompatible():
    """Fall C: At least one descendant with incompatible classification."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "incompatible"),
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is False


def test_all_descendants_compatible_with_deeply_nested_incompatible_grandchild():
    """Fall D: Deeply nested structure with incompatible grandchild."""
    mapping = create_mapping([
        "Patient",
        ("Patient.identifier", "compatible"),
        ("Patient.identifier.system", "compatible"),
        ("Patient.identifier.value", "incompatible"),  # Grandchild is incompatible
        ("Patient.name", "compatible"),
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is False


def test_all_descendants_compatible_checks_only_descendants_not_siblings():
    """Verify that siblings are not checked, only descendants."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.name.family", "compatible"),
        ("Practitioner", "incompatible"),  # Sibling root, should be ignored
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is True


def test_all_descendants_compatible_with_multiple_child_levels():
    """Test with multiple levels of nesting, all compatible."""
    mapping = create_mapping([
        "Patient",
        ("Patient.identifier", "compatible"),
        ("Patient.identifier.system", "compatible"),
        ("Patient.identifier.value", "compatible"),
        ("Patient.identifier.period", "compatible"),
        ("Patient.identifier.period.start", "compatible"),
        ("Patient.identifier.period.end", "compatible"),
    ])

    result = all_descendants_compatible("Patient", mapping)

    assert result is True


# Tests for all_descendants_compatible_or_solved


def test_all_descendants_compatible_or_solved_returns_true_when_all_compatible():
    """Fall E: Like Fall B, all compatible should return True."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.name.family", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])
    evaluation_map: Dict[str, EvaluationResult] = {}

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True


def test_all_descendants_compatible_or_solved_returns_false_for_incompatible_without_evaluation():
    """Fall F: Incompatible descendant with NO entry in evaluation_map."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "incompatible"),
    ])
    evaluation_map: Dict[str, EvaluationResult] = {}  # No evaluation entry

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is False


def test_all_descendants_compatible_or_solved_returns_true_for_incompatible_but_solved():
    """Fall G: Incompatible descendant BUT marked as SOLVED in evaluation_map."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "incompatible"),
    ])
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True


def test_all_descendants_compatible_or_solved_with_mixed_descendants():
    """Fall H: Combination of compatible, solved, and unsolved descendants."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "incompatible"),
        ("Patient.identifier", "incompatible"),
        ("Patient.address", "warning"),
    ])
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        # Patient.identifier has no entry -> NOT solved
        "Patient.address": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            mapping_status=MappingStatus.WARNING  # Not SOLVED
        )
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    # Should be False because Patient.identifier has no evaluation entry
    assert result is False


def test_all_descendants_compatible_or_solved_all_incompatible_all_solved():
    """All descendants are incompatible but all are solved."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "incompatible"),
        ("Patient.birthDate", "incompatible"),
        ("Patient.identifier", "warning"),
    ])
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        "Patient.identifier": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True


def test_all_descendants_compatible_or_solved_with_no_descendants():
    """Field without descendants should return True."""
    mapping = create_mapping([
        "Patient",
    ])
    evaluation_map: Dict[str, EvaluationResult] = {}

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True


def test_all_descendants_compatible_or_solved_with_nested_incompatible_grandchild_solved():
    """Nested structure with incompatible grandchild that is solved."""
    mapping = create_mapping([
        "Patient",
        ("Patient.identifier", "compatible"),
        ("Patient.identifier.system", "compatible"),
        ("Patient.identifier.value", "incompatible"),
    ])
    evaluation_map = {
        "Patient.identifier.value": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True


def test_all_descendants_compatible_or_solved_with_nested_incompatible_grandchild_not_solved():
    """Nested structure with incompatible grandchild that is NOT solved."""
    mapping = create_mapping([
        "Patient",
        ("Patient.identifier", "compatible"),
        ("Patient.identifier.system", "compatible"),
        ("Patient.identifier.value", "incompatible"),
    ])
    evaluation_map = {
        "Patient.identifier.value": EvaluationResult(
            status=EvaluationStatus.INCOMPATIBLE,
            mapping_status=MappingStatus.INCOMPATIBLE
        )
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is False


def test_all_descendants_compatible_or_solved_verifies_missing_evaluation_entry_not_considered_solved():
    """Explicitly test that missing evaluation entries are NOT considered solved."""
    mapping = create_mapping([
        "Patient",
        ("Patient.name", "warning"),  # Not compatible
        ("Patient.birthDate", "incompatible"),  # Not compatible
    ])
    evaluation_map = {
        # Only one field has an entry, the other is missing
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
        # Patient.birthDate has NO entry -> should NOT be considered solved
    }

    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is False


def test_all_descendants_compatible_or_solved_only_checks_descendants_not_parent():
    """Verify that the function checks descendants, not the field itself."""
    mapping = create_mapping([
        ("Patient", "incompatible"),  # Parent itself is incompatible
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])
    evaluation_map: Dict[str, EvaluationResult] = {}

    # Should return True because all DESCENDANTS are compatible
    # (the parent itself is not checked)
    result = all_descendants_compatible_or_solved("Patient", mapping, evaluation_map)

    assert result is True
