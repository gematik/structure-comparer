"""Tests for inherited USE/NOT_USE recommendations."""

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

    def __init__(self, name: str, classification: str = "unknown", actions_allowed=None):
        self.name = name
        self.classification = classification
        self.actions_allowed = actions_allowed


class StubMapping:
    """Minimal mapping stub for testing."""

    def __init__(self, field_data):
        """Create a stub mapping with fields.
        
        Args:
            field_data: Either list of field names or list of tuples (name, classification)
        """
        self.fields: Dict[str, StubField] = {}
        for item in field_data:
            if isinstance(item, tuple):
                name, classification = item
                self.fields[name] = StubField(name, classification)
            else:
                self.fields[item] = StubField(item)


# ========================================
# Tests for USE recommendations
# ========================================


def test_use_action_creates_recommendations_for_all_children():
    """Test that USE action creates USE recommendations for ALL descendant fields (greedy)."""
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
        "Medication.code.coding.system",
        "Medication.code.coding.code",
        "Medication.code.text",
    ])
    
    manual_entries = {
        "Medication.code": {
            "action": "use",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent has USE as manual action
    assert actions["Medication.code"].action == ActionType.USE
    assert actions["Medication.code"].source == ActionSource.MANUAL
    
    # Direct children should have USE recommendations
    assert "Medication.code.coding" in recommendations
    coding_recs = recommendations["Medication.code.coding"]
    use_rec = next((r for r in coding_recs if r.action == ActionType.USE), None)
    assert use_rec is not None
    assert use_rec.auto_generated is True
    assert "Medication.code" in use_rec.system_remarks[0]
    
    # Grandchildren should also have USE recommendations
    assert "Medication.code.coding.system" in recommendations
    system_recs = recommendations["Medication.code.coding.system"]
    use_rec = next((r for r in system_recs if r.action == ActionType.USE), None)
    assert use_rec is not None
    
    assert "Medication.code.coding.code" in recommendations
    code_recs = recommendations["Medication.code.coding.code"]
    use_rec = next((r for r in code_recs if r.action == ActionType.USE), None)
    assert use_rec is not None
    
    assert "Medication.code.text" in recommendations
    text_recs = recommendations["Medication.code.text"]
    use_rec = next((r for r in text_recs if r.action == ActionType.USE), None)
    assert use_rec is not None


def test_use_does_not_create_active_inherited_actions():
    """Test that USE does NOT create active inherited actions, only recommendations."""
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
        "Medication.code.coding.system",
    ])
    
    manual_entries = {
        "Medication.code": {
            "action": "use",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Parent has USE
    assert actions["Medication.code"].action == ActionType.USE
    
    # Children should NOT have inherited USE as active action
    # They should have no action (action=None) until user accepts the recommendation
    child_action = actions["Medication.code.coding"]
    assert child_action.action is None
    assert child_action.source == ActionSource.SYSTEM_DEFAULT


def test_use_manual_child_overrides_recommendation():
    """Test that manual child actions prevent USE recommendations."""
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
        "Medication.code.text",
    ])
    
    manual_entries = {
        "Medication.code": {
            "action": "use",
        },
        # User explicitly set action for .coding
        "Medication.code.coding": {
            "action": "not_use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child with manual action should NOT have recommendation from parent
    assert "Medication.code.coding" not in recommendations
    
    # Sibling without manual action should still have recommendation
    assert "Medication.code.text" in recommendations


# ========================================
# Tests for NOT_USE recommendations
# ========================================


def test_not_use_action_creates_recommendations_for_all_children():
    """Test that NOT_USE action creates NOT_USE recommendations for ALL descendant fields."""
    mapping = StubMapping([
        "Medication.meta",
        "Medication.meta.profile",
        "Medication.meta.versionId",
        "Medication.meta.lastUpdated",
    ])
    
    manual_entries = {
        "Medication.meta": {
            "action": "not_use",
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent has NOT_USE as manual action
    assert actions["Medication.meta"].action == ActionType.NOT_USE
    assert actions["Medication.meta"].source == ActionSource.MANUAL
    
    # All children should have NOT_USE recommendations
    for child_field in ["Medication.meta.profile", "Medication.meta.versionId", "Medication.meta.lastUpdated"]:
        assert child_field in recommendations
        child_recs = recommendations[child_field]
        not_use_rec = next((r for r in child_recs if r.action == ActionType.NOT_USE), None)
        assert not_use_rec is not None
        assert not_use_rec.auto_generated is True
        assert "Medication.meta" in not_use_rec.system_remarks[0]


def test_not_use_does_not_create_active_inherited_actions():
    """Test that NOT_USE does NOT create active inherited actions, only recommendations."""
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
    
    # Child should NOT have inherited NOT_USE as active action
    # (This is the new behavior - NOT_USE is now recommendation only)
    child_action = actions["Medication.meta.profile"]
    assert child_action.action is None
    assert child_action.source == ActionSource.SYSTEM_DEFAULT


def test_not_use_manual_child_overrides_recommendation():
    """Test that manual child actions prevent NOT_USE recommendations."""
    mapping = StubMapping([
        "Medication.meta",
        "Medication.meta.profile",
        "Medication.meta.versionId",
    ])
    
    manual_entries = {
        "Medication.meta": {
            "action": "not_use",
        },
        # User explicitly set different action for .profile
        "Medication.meta.profile": {
            "action": "use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child with manual action should NOT have recommendation from parent
    assert "Medication.meta.profile" not in recommendations
    
    # Sibling without manual action should still have recommendation
    assert "Medication.meta.versionId" in recommendations


# ========================================
# Tests for actions_allowed filtering
# ========================================


def test_use_recommendation_respects_actions_allowed():
    """Test that USE recommendation is not created if USE is not in actions_allowed."""
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
    ])
    
    # Configure field to NOT allow USE action
    mapping.fields["Medication.code.coding"].actions_allowed = [ActionType.FIXED, ActionType.COPY_FROM]
    
    manual_entries = {
        "Medication.code": {
            "action": "use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child should NOT have USE recommendation (not allowed)
    if "Medication.code.coding" in recommendations:
        coding_recs = recommendations["Medication.code.coding"]
        use_recs = [r for r in coding_recs if r.action == ActionType.USE]
        assert len(use_recs) == 0


def test_not_use_recommendation_respects_actions_allowed():
    """Test that NOT_USE recommendation is not created if NOT_USE is not in actions_allowed."""
    mapping = StubMapping([
        "Medication.meta",
        "Medication.meta.profile",
    ])
    
    # Configure field to NOT allow NOT_USE action
    mapping.fields["Medication.meta.profile"].actions_allowed = [ActionType.USE, ActionType.FIXED]
    
    manual_entries = {
        "Medication.meta": {
            "action": "not_use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child should NOT have NOT_USE recommendation (not allowed)
    if "Medication.meta.profile" in recommendations:
        profile_recs = recommendations["Medication.meta.profile"]
        not_use_recs = [r for r in profile_recs if r.action == ActionType.NOT_USE]
        assert len(not_use_recs) == 0


# ========================================
# Tests for deeply nested structures
# ========================================


def test_use_greedy_with_deeply_nested_fields():
    """Test that USE recommendations propagate through multiple levels of nesting."""
    mapping = StubMapping([
        "Patient.name",
        "Patient.name.family",
        "Patient.name.given",
        "Patient.name.extension",
        "Patient.name.extension.url",
        "Patient.name.extension.value[x]",
    ])
    
    manual_entries = {
        "Patient.name": {
            "action": "use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # All descendants at all levels should have USE recommendations
    all_children = [
        "Patient.name.family",
        "Patient.name.given",
        "Patient.name.extension",
        "Patient.name.extension.url",
        "Patient.name.extension.value[x]",
    ]
    
    for child_field in all_children:
        assert child_field in recommendations
        child_recs = recommendations[child_field]
        use_rec = next((r for r in child_recs if r.action == ActionType.USE), None)
        assert use_rec is not None, f"Expected USE recommendation for {child_field}"


def test_not_use_greedy_with_deeply_nested_fields():
    """Test that NOT_USE recommendations propagate through multiple levels of nesting."""
    mapping = StubMapping([
        "Patient.contact",
        "Patient.contact.name",
        "Patient.contact.name.family",
        "Patient.contact.name.given",
        "Patient.contact.telecom",
        "Patient.contact.telecom.system",
        "Patient.contact.telecom.value",
    ])
    
    manual_entries = {
        "Patient.contact": {
            "action": "not_use",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # All descendants at all levels should have NOT_USE recommendations
    all_children = [
        "Patient.contact.name",
        "Patient.contact.name.family",
        "Patient.contact.name.given",
        "Patient.contact.telecom",
        "Patient.contact.telecom.system",
        "Patient.contact.telecom.value",
    ]
    
    for child_field in all_children:
        assert child_field in recommendations
        child_recs = recommendations[child_field]
        not_use_rec = next((r for r in child_recs if r.action == ActionType.NOT_USE), None)
        assert not_use_rec is not None, f"Expected NOT_USE recommendation for {child_field}"
