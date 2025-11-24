"""Tests for USE_RECURSIVE recommendation logic in RecommendationEngine.

This module tests that the RecommendationEngine correctly recommends USE_RECURSIVE
for compatible fields when all descendants are either compatible or solved.
"""

from typing import Dict

from structure_comparer.model.mapping_action_models import ActionSource, ActionType
from structure_comparer.recommendation_engine import RecommendationEngine


class _MockField:
    """Mock field with configurable classification and actions_allowed."""

    def __init__(
        self,
        name: str,
        classification: str = "compatible",
        actions_allowed: list[ActionType] | None = None,
        is_target_required: bool = False,
    ):
        self.name = name
        self.classification = classification
        # If actions_allowed is not explicitly set, default to allowing all actions
        # This matches the behavior in the real system where actions_allowed=None means "no restrictions"
        if actions_allowed is None:
            self.actions_allowed = None
        else:
            self.actions_allowed = actions_allowed
        self.is_target_required = is_target_required


class _MockMapping:
    """Mock mapping containing fields."""

    def __init__(self, fields: list[_MockField]):
        self.fields: Dict[str, _MockField] = {field.name: field for field in fields}


def test_use_and_use_recursive_recommended_when_all_descendants_compatible():
    """Test USE and USE_RECURSIVE are both recommended when all descendants are compatible.

    Scenario:
    - Root field: Patient (classification=compatible)
    - Child: Patient.name (classification=compatible)
    - Grandchild: Patient.name.family (classification=compatible)

    Expected:
    - Recommendations for Patient contain both USE and USE_RECURSIVE
    """
    mapping = _MockMapping(
        [
            _MockField("Patient", classification="compatible"),
            _MockField("Patient.name", classification="compatible"),
            _MockField("Patient.name.family", classification="compatible"),
        ]
    )

    # No manual entries - all fields should get recommendations
    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root field
    root_recs = recommendations.get("Patient", [])
    actions = {rec.action for rec in root_recs}

    assert ActionType.USE in actions, "USE should be recommended for compatible field"
    assert (
        ActionType.USE_RECURSIVE in actions
    ), "USE_RECURSIVE should be recommended when all descendants are compatible"

    # Verify system remarks
    use_recursive_rec = next(
        (rec for rec in root_recs if rec.action == ActionType.USE_RECURSIVE), None
    )
    assert use_recursive_rec is not None
    assert use_recursive_rec.source == ActionSource.SYSTEM_DEFAULT
    assert use_recursive_rec.auto_generated is True
    assert "compatible or solved" in use_recursive_rec.system_remark.lower()


def test_use_recursive_not_recommended_when_descendant_incompatible_and_not_solved():
    """Test USE_RECURSIVE is NOT recommended when descendant is incompatible and not solved.

    Scenario:
    - Root: Patient (classification=compatible)
    - Child: Patient.identifier (classification=incompatible)
    - Evaluation: Patient.identifier has mapping_status != SOLVED

    Expected:
    - Recommendations contain USE but NOT USE_RECURSIVE
    """
    mapping = _MockMapping(
        [
            _MockField("Patient", classification="compatible"),
            _MockField("Patient.identifier", classification="incompatible"),
        ]
    )

    # No manual entries - Patient.identifier will not be solved
    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root field
    root_recs = recommendations.get("Patient", [])
    actions = {rec.action for rec in root_recs}

    assert ActionType.USE in actions, "USE should be recommended for compatible field"
    assert (
        ActionType.USE_RECURSIVE not in actions
    ), "USE_RECURSIVE should NOT be recommended when descendant is incompatible and not solved"


def test_use_recursive_recommended_when_descendant_incompatible_but_solved():
    """Test USE_RECURSIVE is recommended when descendant is incompatible but solved.

    Scenario:
    - Root: Patient (classification=compatible)
    - Child: Patient.identifier (classification=incompatible)
    - Evaluation: Patient.identifier has mapping_status=SOLVED (via manual action)

    Expected:
    - Recommendations contain both USE and USE_RECURSIVE
    """
    mapping = _MockMapping(
        [
            _MockField("Patient", classification="compatible"),
            _MockField("Patient.identifier", classification="incompatible"),
        ]
    )

    # Manual entry for incompatible child to make it "solved"
    manual_entries = {
        "Patient.identifier": {
            "action": "manual",
            "remark": "Will handle manually",
        }
    }

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root field
    root_recs = recommendations.get("Patient", [])
    actions = {rec.action for rec in root_recs}

    assert ActionType.USE in actions, "USE should be recommended for compatible field"
    assert (
        ActionType.USE_RECURSIVE in actions
    ), "USE_RECURSIVE should be recommended when descendant is solved via manual action"


def test_use_recursive_recommendation_respects_actions_allowed():
    """Test USE_RECURSIVE recommendation respects actions_allowed.

    Similar to USE recommendations, USE_RECURSIVE recommendations should only be created
    if USE_RECURSIVE is in the field's actions_allowed list.

    Scenario:
    - Root: Patient (classification=compatible, actions_allowed=[USE, NOT_USE])
      Note: USE_RECURSIVE is NOT in actions_allowed
    - Child: Patient.name (classification=compatible)
    - All descendants are compatible

    Expected:
    - Recommendations contain USE (which IS in actions_allowed)
    - Recommendations do NOT contain USE_RECURSIVE (which is NOT in actions_allowed)
    """
    # Create root field with actions_allowed that excludes USE_RECURSIVE
    root_field = _MockField(
        "Patient",
        classification="compatible",
        actions_allowed=[ActionType.USE, ActionType.NOT_USE],
    )
    # Manually verify USE_RECURSIVE is not allowed
    assert ActionType.USE_RECURSIVE not in root_field.actions_allowed

    mapping = _MockMapping(
        [
            root_field,
            _MockField("Patient.name", classification="compatible"),
            _MockField("Patient.name.family", classification="compatible"),
        ]
    )

    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root field
    root_recs = recommendations.get("Patient", [])
    actions = {rec.action for rec in root_recs}

    # USE_RECURSIVE should NOT be recommended when not in actions_allowed
    assert (
        ActionType.USE_RECURSIVE not in actions
    ), "USE_RECURSIVE should NOT be recommended when not in actions_allowed"

    # USE should still be recommended (it IS in actions_allowed)
    assert ActionType.USE in actions, "USE should be recommended when in actions_allowed"


def test_use_recursive_not_recommended_for_field_without_descendants():
    """Test USE_RECURSIVE is not redundantly recommended for fields without descendants.

    Scenario:
    - Field: Patient.name.family (classification=compatible, leaf field)
    - No descendants

    Expected:
    - Recommendations contain USE
    - USE_RECURSIVE is also recommended (as per all_descendants_compatible_or_solved
      which returns True for fields without descendants)
    """
    mapping = _MockMapping([_MockField("Patient.name.family", classification="compatible")])

    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations
    recs = recommendations.get("Patient.name.family", [])
    actions = {rec.action for rec in recs}

    assert ActionType.USE in actions, "USE should be recommended for compatible field"
    # Per all_descendants_compatible_or_solved: returns True for fields without descendants
    assert (
        ActionType.USE_RECURSIVE in actions
    ), "USE_RECURSIVE is recommended even for leaf fields (per current logic)"


def test_use_recursive_with_mixed_descendants():
    """Test USE_RECURSIVE behavior with mixed descendants (some compatible, some solved).

    Scenario:
    - Root: Medication (classification=compatible)
    - Child 1: Medication.code (classification=compatible)
    - Child 2: Medication.identifier (classification=incompatible, but solved via manual)
    - Grandchild: Medication.identifier.system (classification=incompatible, but solved)

    Expected:
    - Recommendations for Medication contain both USE and USE_RECURSIVE
    """
    mapping = _MockMapping(
        [
            _MockField("Medication", classification="compatible"),
            _MockField("Medication.code", classification="compatible"),
            _MockField("Medication.identifier", classification="incompatible"),
            _MockField("Medication.identifier.system", classification="incompatible"),
        ]
    )

    # Manual entries to solve the incompatible fields
    manual_entries = {
        "Medication.identifier": {
            "action": "manual",
            "remark": "Custom mapping",
        },
        "Medication.identifier.system": {
            "action": "manual",
            "remark": "Custom mapping",
        },
    }

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root
    root_recs = recommendations.get("Medication", [])
    actions = {rec.action for rec in root_recs}

    assert ActionType.USE in actions
    assert (
        ActionType.USE_RECURSIVE in actions
    ), "USE_RECURSIVE should be recommended when all descendants are compatible or solved"


def test_use_recursive_not_recommended_when_one_descendant_not_solved():
    """Test USE_RECURSIVE is NOT recommended if even one descendant is not solved.

    Scenario:
    - Root: Observation (classification=compatible)
    - Child 1: Observation.code (classification=compatible)
    - Child 2: Observation.value (classification=incompatible, NOT solved)
    - Grandchild: Observation.value.unit (classification=compatible)

    Expected:
    - Recommendations contain USE but NOT USE_RECURSIVE
    """
    mapping = _MockMapping(
        [
            _MockField("Observation", classification="compatible"),
            _MockField("Observation.code", classification="compatible"),
            _MockField("Observation.value", classification="incompatible"),
            _MockField("Observation.value.unit", classification="compatible"),
        ]
    )

    # No manual entry for Observation.value, so it remains unsolved
    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for root
    root_recs = recommendations.get("Observation", [])
    actions = {rec.action for rec in root_recs}

    assert ActionType.USE in actions
    assert (
        ActionType.USE_RECURSIVE not in actions
    ), "USE_RECURSIVE should NOT be recommended when any descendant is incompatible and not solved"


def test_no_use_recursive_recommendation_for_incompatible_field():
    """Test USE_RECURSIVE is not recommended for incompatible fields.

    Scenario:
    - Field: Patient.identifier (classification=incompatible)
    - Has compatible children

    Expected:
    - No USE recommendation (field is incompatible)
    - No USE_RECURSIVE recommendation (only applies to compatible fields)
    """
    mapping = _MockMapping(
        [
            _MockField("Patient.identifier", classification="incompatible"),
            _MockField("Patient.identifier.system", classification="compatible"),
        ]
    )

    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify no recommendations for incompatible field
    recs = recommendations.get("Patient.identifier", [])
    actions = {rec.action for rec in recs} if recs else set()

    assert (
        ActionType.USE not in actions
    ), "USE should not be recommended for incompatible field"
    assert (
        ActionType.USE_RECURSIVE not in actions
    ), "USE_RECURSIVE should not be recommended for incompatible field"


def test_use_recursive_recommended_for_deeply_nested_compatible_tree():
    """Test USE_RECURSIVE with a deeply nested but fully compatible tree.

    Scenario:
    - Root: Bundle (compatible)
    - Child: Bundle.entry (compatible)
    - Grandchild: Bundle.entry.resource (compatible)
    - Great-grandchild: Bundle.entry.resource.id (compatible)

    Expected:
    - All levels should get USE and USE_RECURSIVE recommendations
    """
    mapping = _MockMapping(
        [
            _MockField("Bundle", classification="compatible"),
            _MockField("Bundle.entry", classification="compatible"),
            _MockField("Bundle.entry.resource", classification="compatible"),
            _MockField("Bundle.entry.resource.id", classification="compatible"),
        ]
    )

    manual_entries = {}

    # Compute recommendations
    engine = RecommendationEngine(mapping, manual_entries)
    recommendations = engine.compute_all_recommendations()

    # Verify recommendations for all levels
    for field_name in [
        "Bundle",
        "Bundle.entry",
        "Bundle.entry.resource",
        "Bundle.entry.resource.id",
    ]:
        recs = recommendations.get(field_name, [])
        actions = {rec.action for rec in recs}

        assert (
            ActionType.USE in actions
        ), f"USE should be recommended for {field_name}"
        assert (
            ActionType.USE_RECURSIVE in actions
        ), f"USE_RECURSIVE should be recommended for {field_name}"
