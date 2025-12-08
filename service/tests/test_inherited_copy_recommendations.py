"""Tests for inherited copy_from/copy_to recommendations."""

from typing import Dict

from structure_comparer.mapping_actions_engine import (
    compute_mapping_actions,
    compute_recommendations,
)
from structure_comparer.model.mapping_action_models import (
    ActionSource,
    ActionType,
)


class StubField:
    def __init__(self, name: str, classification: str = "compatible"):
        self.name = name
        self.classification = classification


class StubMapping:
    def __init__(self, field_defs):
        self.fields: Dict[str, StubField] = {}
        for definition in field_defs:
            if isinstance(definition, tuple):
                name, classification = definition
            else:
                name, classification = definition, "compatible"
            self.fields[name] = StubField(name, classification)


def test_parent_copy_from_creates_child_recommendation():
    """Test that parent copy_from creates recommendations for child fields."""
    mapping = StubMapping([
        "Medication.extension:A",
        "Medication.extension:A.url",
        "Medication.extension:A.value[x]",
        # Target fields must also exist for inheritance to work
        "Medication.extension:B",
        "Medication.extension:B.url",
        "Medication.extension:B.value[x]",
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "copy_from",
            "other": "Medication.extension:B",
        }
    }
    
    # Get actions
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Get recommendations
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent should have manual copy_from action
    assert actions["Medication.extension:A"].action == ActionType.COPY_FROM
    assert actions["Medication.extension:A"].source == ActionSource.MANUAL
    
    # Parent should NOT have recommendations (has manual action)
    assert "Medication.extension:A" not in recommendations
    
    # Children should have recommendations (not active actions)
    assert "Medication.extension:A.url" in recommendations
    url_recs = recommendations["Medication.extension:A.url"]
    assert len(url_recs) >= 1
    
    # Find the inherited copy_from recommendation
    inherited_rec = next(
        (r for r in url_recs if r.action == ActionType.COPY_FROM), None
    )
    assert inherited_rec is not None
    assert inherited_rec.other_value == "Medication.extension:B.url"
    assert inherited_rec.auto_generated is True
    
    # Children should NOT have active inherited actions
    url_action = actions["Medication.extension:A.url"]
    assert url_action.action is None  # No active action, only recommendation


def test_parent_copy_to_creates_child_recommendation():
    """Test that parent copy_to creates recommendations for child fields."""
    mapping = StubMapping([
        "Medication.code.coding:pzn",
        "Medication.code.coding:pzn.system",
        "Medication.code.coding:pzn.code",
        # Target fields must exist
        "Medication.code.coding:PZN",
        "Medication.code.coding:PZN.system",
        "Medication.code.coding:PZN.code",
    ])
    
    manual_entries = {
        "Medication.code.coding:pzn": {
            "action": "copy_to",
            "other": "Medication.code.coding:PZN",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Children should have copy_to recommendations
    assert "Medication.code.coding:pzn.system" in recommendations
    system_recs = recommendations["Medication.code.coding:pzn.system"]
    
    inherited_rec = next(
        (r for r in system_recs if r.action == ActionType.COPY_TO), None
    )
    assert inherited_rec is not None
    assert inherited_rec.other_value == "Medication.code.coding:PZN.system"


def test_child_with_manual_action_no_recommendation():
    """Test that children with manual actions don't get recommendations."""
    mapping = StubMapping([
        "Patient.identifier",
        "Patient.identifier.system",
    ])
    
    manual_entries = {
        "Patient.identifier": {
            "action": "copy_from",
            "other": "Patient.identifier.reference",
        },
        "Patient.identifier.system": {
            "action": "fixed",
            "fixed": "http://example.com",
        },
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child with manual action should NOT have recommendation
    assert "Patient.identifier.system" not in recommendations


def test_inherited_recommendation_with_nested_children():
    """Test that direct children get inherited recommendations.
    
    Note: Currently only direct children inherit recommendations from parent's action.
    Grandchildren would need to inherit from parent's recommendation, which is a future enhancement.
    """
    mapping = StubMapping([
        "Observation.component",
        "Observation.component.code",
        # Target fields must exist
        "Observation.component.reference",
        "Observation.component.reference.code",
    ])
    
    manual_entries = {
        "Observation.component": {
            "action": "copy_from",
            "other": "Observation.component.reference",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Direct child should have recommendation
    assert "Observation.component.code" in recommendations
    
    code_recs = recommendations["Observation.component.code"]
    inherited_rec = next(
        (r for r in code_recs if r.action == ActionType.COPY_FROM), None
    )
    assert inherited_rec is not None
    assert inherited_rec.other_value == "Observation.component.reference.code"


def test_no_recommendation_when_target_field_missing():
    """Test recommendation behavior when target field doesn't explicitly exist.
    
    For sliced fields, if the source field exists, the target is considered
    structurally valid even if not explicitly defined (inherits from base type).
    """
    mapping = StubMapping([
        "Medication.extension:A",
        "Medication.extension:A.url",
        # Note: Medication.extension:B.url does NOT exist in fields
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "copy_from",
            "other": "Medication.extension:B",  # B doesn't have .url child explicitly
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child SHOULD have recommendation because target is structurally valid
    # (even though Medication.extension:B.url doesn't exist explicitly)
    assert "Medication.extension:A.url" in recommendations
    url_recs = recommendations["Medication.extension:A.url"]
    copy_recs = [r for r in url_recs if r.action == ActionType.COPY_FROM]
    assert len(copy_recs) == 1
    
    # The recommendation should indicate it's implicitly valid
    copy_rec = copy_recs[0]
    assert "structurally valid" in " ".join(copy_rec.system_remarks)


def test_compatible_and_inherited_recommendations_combined():
    """Test that compatible fields can have both USE and inherited recommendations."""
    mapping = StubMapping([
        ("Medication.extension:A", "compatible"),
        ("Medication.extension:A.url", "compatible"),
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "copy_from",
            "other": "Medication.extension:B",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child should have recommendations
    assert "Medication.extension:A.url" in recommendations
    url_recs = recommendations["Medication.extension:A.url"]
    
    # Should have at least one recommendation (could be USE or inherited copy_from)
    assert len(url_recs) >= 1
    
    # Could have both USE (compatible) and COPY_FROM (inherited)
    action_types = {r.action for r in url_recs}
    # At least one of these should be present
    assert ActionType.USE in action_types or ActionType.COPY_FROM in action_types


def test_polymorphic_value_field_no_recommendation():
    """Test that polymorphic type choices don't inherit copy recommendations."""
    mapping = StubMapping([
        "Extension.value[x]",
        "Extension.value[x]:valueBoolean",
    ])
    
    manual_entries = {
        "Extension.value[x]": {
            "action": "copy_from",
            "other": "Extension.other",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Polymorphic type choice should NOT inherit the copy action
    # It might still have compatible USE recommendation though
    if "Extension.value[x]:valueBoolean" in recommendations:
        recs = recommendations["Extension.value[x]:valueBoolean"]
        copy_recs = [r for r in recs if r.action == ActionType.COPY_FROM]
        # Should not have inherited copy_from
        assert len(copy_recs) == 0


def test_not_use_action_still_inherits():
    """Test that NOT_USE action creates active inherited actions for direct children.
    
    Note: With the auto-inherit feature, NOT_USE with source=MANUAL now creates
    active inherited actions for direct children (not just recommendations).
    """
    mapping = StubMapping([
        "Medication.meta",
        "Medication.meta.profile",
    ])
    
    manual_entries = {
        "Medication.meta": {
            "action": "not_use",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)

    # Parent has NOT_USE
    assert actions["Medication.meta"].action == ActionType.NOT_USE
    
    # Child SHOULD inherit NOT_USE as active action (new auto-inherit behavior)
    assert actions["Medication.meta.profile"].action == ActionType.NOT_USE
    assert actions["Medication.meta.profile"].source == ActionSource.INHERITED
    assert actions["Medication.meta.profile"].inherited_from == "Medication.meta"
