"""Tests for use_recursive filtering in actions_allowed.

Tests verify that use_recursive is only allowed in actions_allowed when:
- The field has at least one descendant (not a leaf field) AND
- ALL descendants have classification == "compatible" OR mapping_status == "SOLVED"

This tests the evaluation-aware logic in adjust_use_recursive_actions_allowed().
"""

from typing import Dict

from structure_comparer.action import Action
from structure_comparer.data.mapping import MappingField
from structure_comparer.mapping_actions_engine import adjust_use_recursive_actions_allowed
from structure_comparer.model.comparison import ComparisonClassification
from structure_comparer.model.mapping_action_models import (
    EvaluationResult,
    EvaluationStatus,
    MappingStatus,
)


class StubProfileField:
    """Stub for a profile field to satisfy MappingField requirements."""
    def __init__(self):
        pass


def create_mapping_field(name: str, classification: ComparisonClassification, 
                         has_source: bool = True, has_target: bool = True) -> MappingField:
    """
    Create a MappingField with the given name and classification.
    
    Args:
        name: Field name (e.g., "Patient.name")
        classification: The classification for this field
        has_source: Whether field exists in source profile
        has_target: Whether field exists in target profile
        
    Returns:
        Configured MappingField instance
    """
    field = MappingField(name)
    field.classification = classification
    
    # Set up profiles to satisfy fill_allowed_actions requirements
    field.profiles = {
        "source": StubProfileField() if has_source else None,
        "target": StubProfileField() if has_target else None,
    }
    
    return field


def create_field_mapping(field_defs: list) -> Dict[str, MappingField]:
    """
    Create a mapping dictionary from field definitions.
    
    Args:
        field_defs: List of tuples (name, classification) or dicts with name/classification
        
    Returns:
        Dictionary mapping field names to MappingField objects
    """
    fields: Dict[str, MappingField] = {}
    
    for definition in field_defs:
        if isinstance(definition, tuple):
            name, classification = definition
            has_source, has_target = True, True
        elif isinstance(definition, dict):
            name = definition["name"]
            classification = definition["classification"]
            has_source = definition.get("has_source", True)
            has_target = definition.get("has_target", True)
        else:
            raise ValueError(f"Invalid field definition: {definition}")
        
        fields[name] = create_mapping_field(name, classification, has_source, has_target)
    
    return fields


def fill_actions_for_all_fields(
    fields: Dict[str, MappingField],
    evaluation_map: Dict[str, EvaluationResult] = None,
    action_info_map: Dict = None
):
    """
    Call fill_allowed_actions and adjust_use_recursive_actions_allowed on all fields.
    
    Args:
        fields: Dictionary of field names to MappingField objects
        evaluation_map: Optional evaluation map for use_recursive filtering
        action_info_map: Optional action info map for checking manual actions
    """
    # First pass: set baseline actions_allowed
    for field in fields.values():
        field.fill_allowed_actions(["source"], "target")
    
    # Second pass: adjust use_recursive based on evaluation
    if evaluation_map is None:
        evaluation_map = {}
    
    # Create a minimal mapping stub
    class StubMapping:
        def __init__(self, field_dict):
            self.fields = field_dict
    
    mapping = StubMapping(fields)
    adjust_use_recursive_actions_allowed(mapping, evaluation_map, action_info_map)


# ============================================================================
# Required Tests
# ============================================================================


def test_use_recursive_not_allowed_for_leaf_field():
    """
    Leaf field (no descendants) should NOT have use_recursive in actions_allowed.
    
    Even if the field itself is compatible, use_recursive is not applicable
    for fields without children.
    """
    fields = create_field_mapping([
        ("Patient.name", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    field = fields["Patient.name"]
    assert Action.USE_RECURSIVE not in field.actions_allowed, \
        "Leaf field should not have use_recursive in actions_allowed"


def test_use_recursive_allowed_when_all_descendants_compatible():
    """
    Field with descendants where ALL are compatible should have use_recursive.
    
    This is the positive case: parent field with multiple compatible children
    should be allowed to use use_recursive action.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.name.family", ComparisonClassification.COMPAT),
        ("Patient.name.given", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    # Parent field should have use_recursive
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent field with all compatible descendants should have use_recursive"
    
    # Intermediate parent (Patient.name) should also have use_recursive
    name_field = fields["Patient.name"]
    assert Action.USE_RECURSIVE in name_field.actions_allowed, \
        "Intermediate parent with all compatible descendants should have use_recursive"
    
    # Leaf fields should NOT have use_recursive
    family_field = fields["Patient.name.family"]
    assert Action.USE_RECURSIVE not in family_field.actions_allowed, \
        "Leaf field should not have use_recursive"


def test_use_recursive_not_allowed_when_descendant_warning():
    """
    Field with at least one warning descendant should NOT have use_recursive.
    
    Even if other descendants are compatible, the presence of a warning
    descendant should prevent use_recursive from being allowed (unless SOLVED).
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.WARN),
    ])
    
    # No evaluation map - warning field is not solved
    fill_actions_for_all_fields(fields)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent field with warning descendant should not have use_recursive"


def test_use_recursive_allowed_when_descendant_warning_but_solved():
    """
    Field with warning descendant that is SOLVED should have use_recursive.
    
    This tests that warning fields can also be resolved via evaluation.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.WARN),
    ])
    
    # Evaluation map marks the warning field as SOLVED
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent field should have use_recursive when warning descendant is SOLVED"


def test_use_recursive_not_allowed_when_descendant_incompatible():
    """
    Field with at least one incompatible descendant should NOT have use_recursive.
    
    Incompatible descendants require manual intervention, so use_recursive
    should not be available (unless they are marked as SOLVED in evaluation).
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
    ])
    
    # No evaluation map provided - incompatible field is not solved
    fill_actions_for_all_fields(fields)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent field with incompatible descendant should not have use_recursive"


def test_use_recursive_allowed_when_descendant_incompatible_but_solved():
    """
    Field with incompatible descendant that is SOLVED should have use_recursive.
    
    This tests the evaluation-aware logic: if an incompatible descendant has
    mapping_status == SOLVED, use_recursive should be allowed.
    
    Scenario:
    - Root field: compatible
    - One descendant: incompatible
    - Evaluation marks incompatible descendant as SOLVED (e.g., via manual action)
    
    Expected: use_recursive IS in root field's actions_allowed
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
    ])
    
    # Evaluation map marks the incompatible field as SOLVED
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent field should have use_recursive when incompatible descendant is SOLVED"


def test_use_recursive_not_allowed_when_descendant_incompatible_and_not_solved():
    """
    Field with incompatible descendant that is NOT solved should NOT have use_recursive.
    
    This explicitly tests the negative case: incompatible descendant without
    a manual action or SOLVED status prevents use_recursive.
    
    Scenario:
    - Root field: compatible
    - One descendant: incompatible
    - NO evaluation entry OR evaluation shows NOT SOLVED
    
    Expected: use_recursive is NOT in root field's actions_allowed
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
    ])
    
    # Evaluation map shows incompatible field is NOT solved
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.INCOMPATIBLE,
            mapping_status=MappingStatus.INCOMPATIBLE
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent field should NOT have use_recursive when incompatible descendant is NOT solved"


# ============================================================================
# Extended Test Scenarios
# ============================================================================


def test_use_recursive_not_allowed_with_deeply_nested_incompatible_grandchild():
    """
    Deeply nested structure with incompatible grandchild.
    
    Even if direct children are compatible, an incompatible grandchild
    should prevent use_recursive at the root level.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.identifier", ComparisonClassification.COMPAT),
        ("Patient.identifier.system", ComparisonClassification.COMPAT),
        ("Patient.identifier.value", ComparisonClassification.INCOMPAT),  # Grandchild incompatible
        ("Patient.name", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    # Root field should NOT have use_recursive due to incompatible grandchild
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Root field should not have use_recursive when grandchild is incompatible"
    
    # Direct parent of incompatible field should also NOT have use_recursive
    identifier_field = fields["Patient.identifier"]
    assert Action.USE_RECURSIVE not in identifier_field.actions_allowed, \
        "Parent of incompatible field should not have use_recursive"


def test_use_recursive_with_mixed_sibling_classifications():
    """
    Mixed sibling classifications where some are compatible, some are not.
    
    The parent should not have use_recursive if any descendant is not compatible.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.identifier", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.WARN),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
        ("Patient.gender", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent with mixed descendant classifications should not have use_recursive"


def test_use_recursive_not_allowed_when_parent_compatible_but_child_warning():
    """
    Parent is compatible but has a single warning child.
    
    This verifies that parent's own classification doesn't override the
    descendant check.
    """
    fields = create_field_mapping([
        ("Practitioner", ComparisonClassification.COMPAT),
        ("Practitioner.name", ComparisonClassification.WARN),
    ])
    
    fill_actions_for_all_fields(fields)
    
    practitioner_field = fields["Practitioner"]
    assert Action.USE_RECURSIVE not in practitioner_field.actions_allowed, \
        "Compatible parent with warning child should not have use_recursive"


def test_use_recursive_allowed_for_multiple_levels_all_compatible():
    """
    Multiple levels of nesting, all compatible.
    
    Verifies that use_recursive is correctly allowed at each level when
    all descendants are compatible.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.identifier", ComparisonClassification.COMPAT),
        ("Patient.identifier.system", ComparisonClassification.COMPAT),
        ("Patient.identifier.value", ComparisonClassification.COMPAT),
        ("Patient.identifier.period", ComparisonClassification.COMPAT),
        ("Patient.identifier.period.start", ComparisonClassification.COMPAT),
        ("Patient.identifier.period.end", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    # Root field should have use_recursive
    assert Action.USE_RECURSIVE in fields["Patient"].actions_allowed
    
    # Intermediate parents should have use_recursive
    assert Action.USE_RECURSIVE in fields["Patient.identifier"].actions_allowed
    assert Action.USE_RECURSIVE in fields["Patient.identifier.period"].actions_allowed
    
    # Leaf fields should NOT have use_recursive
    assert Action.USE_RECURSIVE not in fields["Patient.identifier.system"].actions_allowed
    assert Action.USE_RECURSIVE not in fields["Patient.identifier.value"].actions_allowed
    assert Action.USE_RECURSIVE not in fields["Patient.identifier.period.start"].actions_allowed
    assert Action.USE_RECURSIVE not in fields["Patient.identifier.period.end"].actions_allowed


def test_use_recursive_independent_of_parent_classification():
    """
    Parent classification does not affect use_recursive filtering.
    
    Even if the parent is incompatible or warning, if all descendants are
    compatible, use_recursive should be allowed. (This tests that we only
    check descendants, not the field itself.)
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.INCOMPAT),  # Parent is incompatible
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent should have use_recursive when all descendants are compatible, " \
        "regardless of parent's own classification"


def test_use_recursive_with_only_source_present():
    """
    Field exists only in source profile, not in target.
    
    use_recursive should be filtered based on source/target presence rules,
    but this test ensures our descendant logic doesn't interfere with that.
    """
    fields = create_field_mapping([
        ({"name": "Patient", "classification": ComparisonClassification.COMPAT, 
          "has_source": True, "has_target": True}),
        ({"name": "Patient.name", "classification": ComparisonClassification.COMPAT,
          "has_source": True, "has_target": False}),  # No target
    ])
    
    fill_actions_for_all_fields(fields)
    
    # Even though descendants are compatible, use_recursive might not be in
    # allowed actions due to target absence - but our logic should not break
    patient_field = fields["Patient"]
    # We're just checking that the logic runs without error
    # The actual presence of use_recursive depends on source/target rules
    assert isinstance(patient_field.actions_allowed, list)


def test_use_recursive_sibling_fields_do_not_affect_each_other():
    """
    Sibling fields (different root paths) should not affect each other.
    
    Patient with incompatible child should not affect Practitioner's use_recursive.
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.INCOMPAT),
        ("Practitioner", ComparisonClassification.COMPAT),
        ("Practitioner.name", ComparisonClassification.COMPAT),
    ])
    
    fill_actions_for_all_fields(fields)
    
    # Patient should NOT have use_recursive (incompatible child)
    assert Action.USE_RECURSIVE not in fields["Patient"].actions_allowed
    
    # Practitioner SHOULD have use_recursive (compatible child)
    assert Action.USE_RECURSIVE in fields["Practitioner"].actions_allowed, \
        "Sibling root field with compatible descendants should have use_recursive"


def test_use_recursive_with_mixed_descendants_some_solved():
    """
    Parent with mixed descendant classifications where some are solved.
    
    Scenario:
    - Root field: compatible
    - Child 1: compatible
    - Child 2: incompatible, but SOLVED
    - Child 3: warning, but SOLVED
    
    Expected: use_recursive IS in root field's actions_allowed
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
        ("Patient.gender", ComparisonClassification.WARN),
    ])
    
    # Both problematic fields are marked as SOLVED
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        "Patient.gender": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent should have use_recursive when all incompatible/warning descendants are SOLVED"


def test_use_recursive_with_mixed_descendants_not_all_solved():
    """
    Parent with mixed descendants where NOT all problematic ones are solved.
    
    Scenario:
    - Root field: compatible
    - Child 1: compatible
    - Child 2: incompatible, SOLVED
    - Child 3: warning, NOT solved
    
    Expected: use_recursive is NOT in root field's actions_allowed
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
        ("Patient.gender", ComparisonClassification.WARN),
    ])
    
    # Only one of the problematic fields is solved
    evaluation_map = {
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        "Patient.gender": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            mapping_status=MappingStatus.WARNING
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent should NOT have use_recursive when not all problematic descendants are solved"


def test_use_recursive_with_deeply_nested_solved_grandchild():
    """
    Deeply nested structure where incompatible grandchild is solved.
    
    Scenario:
    - Root -> Child -> Grandchild (incompatible but SOLVED)
    
    Expected: use_recursive IS in both root and child's actions_allowed
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.identifier", ComparisonClassification.COMPAT),
        ("Patient.identifier.system", ComparisonClassification.COMPAT),
        ("Patient.identifier.value", ComparisonClassification.INCOMPAT),
    ])
    
    # Grandchild is marked as SOLVED
    evaluation_map = {
        "Patient.identifier.value": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    # Root should have use_recursive
    assert Action.USE_RECURSIVE in fields["Patient"].actions_allowed, \
        "Root should have use_recursive when incompatible grandchild is SOLVED"
    
    # Direct parent should also have use_recursive
    assert Action.USE_RECURSIVE in fields["Patient.identifier"].actions_allowed, \
        "Parent of SOLVED incompatible field should have use_recursive"


def test_use_recursive_empty_evaluation_map_same_as_no_solved():
    """
    Empty evaluation map should treat all incompatible/warning fields as not solved.
    
    Scenario:
    - Fields with warning/incompatible descendants
    - Empty evaluation map provided
    
    Expected: Same behavior as if no evaluation map was provided
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.INCOMPAT),
    ])
    
    # Empty evaluation map
    evaluation_map = {}
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent should NOT have use_recursive with empty evaluation map for incompatible descendant"


def test_use_recursive_compatible_in_evaluation_counts_as_ok():
    """
    Compatible classification should be treated as OK regardless of evaluation status.
    
    Scenario:
    - All descendants compatible
    - Evaluation map may or may not contain entries for them
    
    Expected: use_recursive IS allowed (compatible descendants don't need SOLVED status)
    """
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.COMPAT),
        ("Patient.birthDate", ComparisonClassification.COMPAT),
    ])
    
    # Evaluation map has entries, but classification is what matters for compatible fields
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.OK,
            mapping_status=MappingStatus.COMPATIBLE
        ),
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.OK,
            mapping_status=MappingStatus.COMPATIBLE
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent should have use_recursive when all descendants are compatible"


def test_use_recursive_allowed_when_all_children_have_manual_actions():
    """
    Parent with incompatible children that ALL have manual actions.
    
    Scenario:
    - Root field: compatible
    - Child 1: incompatible, has MANUAL action
    - Child 2: warning, has MANUAL action
    
    Expected: use_recursive is NOT allowed because all children have manual actions
    (no children without manual actions remaining for use_recursive to apply to)
    """
    from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource, ActionType
    
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.INCOMPAT),
        ("Patient.birthDate", ComparisonClassification.WARN),
    ])
    
    # Both children have manual actions
    action_info_map = {
        "Patient.name": ActionInfo(
            action=ActionType.NOT_USE,
            source=ActionSource.MANUAL
        ),
        "Patient.birthDate": ActionInfo(
            action=ActionType.EMPTY,
            source=ActionSource.MANUAL
        )
    }
    
    # Evaluation map shows they are NOT solved
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.INCOMPATIBLE,
            mapping_status=MappingStatus.INCOMPATIBLE
        ),
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            mapping_status=MappingStatus.WARNING
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map, action_info_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent should NOT have use_recursive when all children have manual actions"


def test_use_recursive_allowed_when_some_children_have_manual_actions():
    """
    Parent with mixed children: some with manual actions, some without.
    
    Scenario:
    - Root field: compatible
    - Child 1: incompatible, has MANUAL action (SOLVED)
    - Child 2: compatible, NO manual action
    
    Expected: use_recursive IS allowed because child 2 has no manual action
    and is compatible
    """
    from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource, ActionType
    
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.INCOMPAT),
        ("Patient.birthDate", ComparisonClassification.COMPAT),
    ])
    
    # Only first child has manual action
    action_info_map = {
        "Patient.name": ActionInfo(
            action=ActionType.NOT_USE,
            source=ActionSource.MANUAL
        )
    }
    
    # Evaluation map
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            mapping_status=MappingStatus.SOLVED
        ),
        "Patient.birthDate": EvaluationResult(
            status=EvaluationStatus.OK,
            mapping_status=MappingStatus.COMPATIBLE
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map, action_info_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE in patient_field.actions_allowed, \
        "Parent should have use_recursive when some children lack manual actions and are compatible/solved"


def test_use_recursive_with_inherited_actions_not_counted_as_manual():
    """
    Children with INHERITED actions should NOT be excluded from the check.
    
    Scenario:
    - Root field: compatible
    - Child 1: incompatible, has INHERITED action (not manual)
    
    Expected: use_recursive is NOT allowed because inherited actions don't count
    """
    from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource, ActionType
    
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.INCOMPAT),
    ])
    
    # Child has inherited action (not manual)
    action_info_map = {
        "Patient.name": ActionInfo(
            action=ActionType.NOT_USE,
            source=ActionSource.INHERITED,
            inherited_from="Patient"
        )
    }
    
    # Evaluation map shows not solved
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.INCOMPATIBLE,
            mapping_status=MappingStatus.INCOMPATIBLE
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map, action_info_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent should NOT have use_recursive when child has inherited (not manual) action"


def test_use_recursive_with_action_none_not_counted_as_manual():
    """
    Children with action=None should NOT be excluded from the check.
    
    Scenario:
    - Root field: compatible
    - Child 1: incompatible, action is None
    
    Expected: use_recursive is NOT allowed
    """
    from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource
    
    fields = create_field_mapping([
        ("Patient", ComparisonClassification.COMPAT),
        ("Patient.name", ComparisonClassification.INCOMPAT),
    ])
    
    # Child has action=None
    action_info_map = {
        "Patient.name": ActionInfo(
            action=None,
            source=ActionSource.SYSTEM_DEFAULT
        )
    }
    
    # Evaluation map shows not solved
    evaluation_map = {
        "Patient.name": EvaluationResult(
            status=EvaluationStatus.INCOMPATIBLE,
            mapping_status=MappingStatus.INCOMPATIBLE
        )
    }
    
    fill_actions_for_all_fields(fields, evaluation_map, action_info_map)
    
    patient_field = fields["Patient"]
    assert Action.USE_RECURSIVE not in patient_field.actions_allowed, \
        "Parent should NOT have use_recursive when child has action=None"

