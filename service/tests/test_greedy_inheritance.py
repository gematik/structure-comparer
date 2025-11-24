"""Tests for greedy inheritance of copy_to/copy_from and use_recursive actions."""

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
    """Minimal field stub for testing."""

    def __init__(self, name: str, classification: str = "compatible"):
        self.name = name
        self.classification = classification
        self.actions_allowed = None  # Allow all actions


class StubMapping:
    """Minimal mapping stub for testing."""

    def __init__(self, field_names: list):
        self.fields: Dict[str, StubField] = {}
        for name in field_names:
            if isinstance(name, tuple):
                field_name, classification = name
                self.fields[field_name] = StubField(field_name, classification)
            else:
                self.fields[name] = StubField(name)
        self.target = None


# ========================================
# Tests for greedy copy_to inheritance
# ========================================


def test_copy_to_greedy_creates_recommendations_for_all_children():
    """Test that copy_to creates recommendations for ALL descendant fields (greedy)."""
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.id",
        "Practitioner.identifier:ANR.extension",
        "Practitioner.identifier:ANR.extension.url",
        "Practitioner.identifier:ANR.use",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:ANR.value",
        "Practitioner.identifier:LANR",
        "Practitioner.identifier:LANR.id",
        "Practitioner.identifier:LANR.extension",
        "Practitioner.identifier:LANR.extension.url",
        "Practitioner.identifier:LANR.use",
        "Practitioner.identifier:LANR.system",
        "Practitioner.identifier:LANR.value",
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_to",
            "other": "Practitioner.identifier:LANR",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent has COPY_TO as manual action
    assert actions["Practitioner.identifier:ANR"].action == ActionType.COPY_TO
    assert actions["Practitioner.identifier:ANR"].source == ActionSource.MANUAL
    
    # Direct children should have COPY_TO recommendations
    assert "Practitioner.identifier:ANR.id" in recommendations
    id_recs = recommendations["Practitioner.identifier:ANR.id"]
    copy_to_rec = next((r for r in id_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.id"
    
    assert "Practitioner.identifier:ANR.extension" in recommendations
    ext_recs = recommendations["Practitioner.identifier:ANR.extension"]
    copy_to_rec = next((r for r in ext_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.extension"
    
    assert "Practitioner.identifier:ANR.use" in recommendations
    use_recs = recommendations["Practitioner.identifier:ANR.use"]
    copy_to_rec = next((r for r in use_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.use"
    
    assert "Practitioner.identifier:ANR.system" in recommendations
    system_recs = recommendations["Practitioner.identifier:ANR.system"]
    copy_to_rec = next((r for r in system_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.system"
    
    assert "Practitioner.identifier:ANR.value" in recommendations
    value_recs = recommendations["Practitioner.identifier:ANR.value"]
    copy_to_rec = next((r for r in value_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.value"
    
    # Grandchildren (nested fields) should also have recommendations
    assert "Practitioner.identifier:ANR.extension.url" in recommendations
    url_recs = recommendations["Practitioner.identifier:ANR.extension.url"]
    copy_to_rec = next((r for r in url_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.extension.url"


def test_copy_from_greedy_creates_recommendations_for_all_children():
    """Test that copy_from creates recommendations for ALL descendant fields (greedy)."""
    mapping = StubMapping([
        "Medication.extension:A",
        "Medication.extension:A.url",
        "Medication.extension:A.value[x]",
        "Medication.extension:A.value[x]:valueString",
        "Medication.extension:B",
        "Medication.extension:B.url",
        "Medication.extension:B.value[x]",
        "Medication.extension:B.value[x]:valueString",
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "copy_from",
            "other": "Medication.extension:B",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # All children should have COPY_FROM recommendations
    assert "Medication.extension:A.url" in recommendations
    url_recs = recommendations["Medication.extension:A.url"]
    copy_from_rec = next((r for r in url_recs if r.action == ActionType.COPY_FROM), None)
    assert copy_from_rec is not None
    assert copy_from_rec.other_value == "Medication.extension:B.url"
    
    assert "Medication.extension:A.value[x]" in recommendations
    value_recs = recommendations["Medication.extension:A.value[x]"]
    copy_from_rec = next((r for r in value_recs if r.action == ActionType.COPY_FROM), None)
    assert copy_from_rec is not None
    assert copy_from_rec.other_value == "Medication.extension:B.value[x]"
    
    # Grandchildren should also have recommendations
    assert "Medication.extension:A.value[x]:valueString" in recommendations
    str_recs = recommendations["Medication.extension:A.value[x]:valueString"]
    copy_from_rec = next((r for r in str_recs if r.action == ActionType.COPY_FROM), None)
    assert copy_from_rec is not None
    assert copy_from_rec.other_value == "Medication.extension:B.value[x]:valueString"


def test_copy_to_no_active_inherited_actions():
    """Test that copy_to does NOT create active inherited actions, only recommendations."""
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:LANR",
        "Practitioner.identifier:LANR.system",
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_to",
            "other": "Practitioner.identifier:LANR",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Parent has COPY_TO
    assert actions["Practitioner.identifier:ANR"].action == ActionType.COPY_TO
    
    # Child should NOT have inherited COPY_TO as active action
    # It should have no action (action=None) until user accepts the recommendation
    child_action = actions["Practitioner.identifier:ANR.system"]
    assert child_action.action is None
    assert child_action.source == ActionSource.SYSTEM_DEFAULT


# ========================================
# Tests for greedy use_recursive inheritance
# ========================================


def test_use_recursive_greedy_creates_use_recommendations_for_all_children():
    """Test that use_recursive creates USE recommendations for ALL descendant fields."""
    mapping = StubMapping([
        "Medication.extension:A",
        "Medication.extension:A.id",
        "Medication.extension:A.url",
        "Medication.extension:A.value[x]",
        "Medication.extension:A.value[x]:valueString",
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "use_recursive",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent has USE_RECURSIVE as active action
    assert actions["Medication.extension:A"].action == ActionType.USE_RECURSIVE
    assert actions["Medication.extension:A"].source == ActionSource.MANUAL
    
    # Direct children should have USE_RECURSIVE as inherited active actions
    # (because USE_RECURSIVE is in _INHERITABLE_ACTIONS)
    assert actions["Medication.extension:A.id"].action == ActionType.USE_RECURSIVE
    assert actions["Medication.extension:A.id"].source == ActionSource.INHERITED
    
    # Children without manual entries should also have USE recommendations
    # (either from compatible status or from USE_RECURSIVE parent)
    assert "Medication.extension:A.id" in recommendations
    id_recs = recommendations["Medication.extension:A.id"]
    # Should have at least one USE recommendation
    use_rec = next((r for r in id_recs if r.action == ActionType.USE), None)
    assert use_rec is not None
    
    # Same for all other descendants
    assert "Medication.extension:A.url" in recommendations
    assert "Medication.extension:A.value[x]" in recommendations
    assert "Medication.extension:A.value[x]:valueString" in recommendations


def test_use_does_not_create_recommendations_for_children():
    """Test that plain USE creates recommendations for children (new behavior)."""
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
        "Medication.code.coding.system",
        "Medication.code.text",
    ])
    
    manual_entries = {
        "Medication.code": {
            "action": "use",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent has USE
    assert actions["Medication.code"].action == ActionType.USE
    
    # Children should NOT inherit USE as active action (USE is not in _INHERITABLE_ACTIONS)
    assert actions["Medication.code.coding"].action is None
    assert actions["Medication.code.text"].action is None
    
    # Children SHOULD have USE recommendations from parent (new behavior)
    assert "Medication.code.coding" in recommendations
    coding_recs = recommendations["Medication.code.coding"]
    use_recs = [r for r in coding_recs if r.action == ActionType.USE]
    assert len(use_recs) > 0
    
    # Check that at least one recommendation mentions the parent
    parent_mentioned = any(
        rec.system_remarks and "Medication.code" in rec.system_remarks[0]
        for rec in use_recs
    )
    assert parent_mentioned, "Expected at least one USE recommendation to mention parent field"


def test_manual_child_overrides_greedy_recommendation():
    """Test that manual child actions prevent greedy recommendations."""
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:ANR.value",
        "Practitioner.identifier:LANR",
        "Practitioner.identifier:LANR.system",
        "Practitioner.identifier:LANR.value",
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_to",
            "other": "Practitioner.identifier:LANR",
        },
        # User explicitly set action for .system
        "Practitioner.identifier:ANR.system": {
            "action": "fixed",
            "fixed": "http://example.com/system",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # .system has manual action, so should NOT get copy_to recommendation
    assert "Practitioner.identifier:ANR.system" not in recommendations
    
    # But .value should still get the recommendation
    assert "Practitioner.identifier:ANR.value" in recommendations
    value_recs = recommendations["Practitioner.identifier:ANR.value"]
    copy_to_rec = next((r for r in value_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.value"


def test_greedy_stops_at_missing_target_field():
    """Test greedy inheritance for sliced fields with implicit target children.
    
    For FHIR slices: if the source slice has a child field, the target slice
    should structurally support the same child (inherits from base type).
    """
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.id",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:LANR",
        # Note: LANR.id exists but LANR.system does NOT
        "Practitioner.identifier:LANR.id",
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_to",
            "other": "Practitioner.identifier:LANR",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # .id should get recommendation (target exists)
    assert "Practitioner.identifier:ANR.id" in recommendations
    id_recs = recommendations["Practitioner.identifier:ANR.id"]
    copy_to_rec = next((r for r in id_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None
    
    # .system should ALSO get recommendation (implicit slice - structurally valid)
    assert "Practitioner.identifier:ANR.system" in recommendations
    system_recs = recommendations["Practitioner.identifier:ANR.system"]
    copy_to_rec = next((r for r in system_recs if r.action == ActionType.COPY_TO), None)
    assert copy_to_rec is not None  # Recommendation created via implicit slice fallback
    assert copy_to_rec.other_value == "Practitioner.identifier:LANR.system"
    # Check that the remarks indicate it's an implicit slice
    assert copy_to_rec.system_remarks is not None
    assert any("not explicitly defined" in remark for remark in copy_to_rec.system_remarks)
