from typing import Dict

from structure_comparer.mapping_actions_engine import compute_mapping_actions, compute_recommendations
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
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


def test_manual_action_overrides_everything():
    mapping = StubMapping(["Practitioner.name"])
    manual_entries = {
        "Practitioner.name": {
            "action": "not_use",
            "remark": "User decision",
        }
    }

    result = compute_mapping_actions(mapping, manual_entries)
    field_action: ActionInfo = result["Practitioner.name"]

    assert field_action.action == ActionType.NOT_USE
    assert field_action.source == ActionSource.MANUAL
    assert field_action.user_remark == "User decision"
    assert field_action.auto_generated is False


def test_parent_not_use_is_inherited_by_children():
    """Test that NOT_USE creates recommendations (not inherited actions) for children.
    
    Note: NOT_USE is no longer in _INHERITABLE_ACTIONS, so it creates recommendations
    instead of active inherited actions.
    """
    mapping = StubMapping([
        "Patient.identifier",
        "Patient.identifier.system",
    ])
    manual_entries = {
        "Patient.identifier": {
            "action": "not_use",
        }
    }

    actions = compute_mapping_actions(mapping, manual_entries)
    recommendations = compute_recommendations(mapping, manual_entries)

    parent_info = actions["Patient.identifier"]
    child_info = actions["Patient.identifier.system"]

    assert parent_info.action == ActionType.NOT_USE
    assert parent_info.source == ActionSource.MANUAL

    # Child should NOT have inherited NOT_USE as active action (new behavior)
    assert child_info.action is None
    assert child_info.source == ActionSource.SYSTEM_DEFAULT
    
    # Child should have NOT_USE as recommendation
    assert "Patient.identifier.system" in recommendations
    recs = recommendations["Patient.identifier.system"]
    not_use_recs = [r for r in recs if r.action == ActionType.NOT_USE]
    assert len(not_use_recs) == 1


def test_system_default_action_fills_missing_entries():
    """Compatible fields without manual actions should get None action (not USE).
    
    Note: Compatible fields now receive recommendations instead of active USE actions.
    This ensures they don't automatically become 'solved' status.
    """
    mapping = StubMapping(["Observation.code"])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.code"]
    assert field_action.action is None  # Changed from ActionType.USE
    assert field_action.source == ActionSource.SYSTEM_DEFAULT
    assert field_action.auto_generated is True


def test_incompatible_field_without_manual_action_has_no_use_default():
    """Incompatible fields without manual actions should get None action.
    
    User must explicitly select an action for incompatible fields.
    """
    mapping = StubMapping([
        ("Observation.value", "incompatible"),
    ])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.value"]
    assert field_action.action is None  # Changed from ActionType.OTHER
    assert field_action.source == ActionSource.SYSTEM_DEFAULT
    assert field_action.auto_generated is True


def test_warning_field_without_manual_action_has_no_use_default():
    """Warning fields without manual actions should get None action.
    
    User must explicitly select an action for warning fields.
    """
    mapping = StubMapping([
        ("Observation.note", "warning"),
    ])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.note"]
    assert field_action.action is None  # Changed from ActionType.OTHER
    assert field_action.source == ActionSource.SYSTEM_DEFAULT


def test_manual_child_action_prevents_inheritance():
    mapping = StubMapping([
        "Practitioner.meta",
        "Practitioner.meta.profile",
    ])
    manual_entries = {
        "Practitioner.meta": {"action": "not_use"},
        "Practitioner.meta.profile": {
            "action": "use",  # Changed from "extension" (which doesn't exist)
            "remark": "Child override",
        },
    }

    result = compute_mapping_actions(mapping, manual_entries)

    child_info = result["Practitioner.meta.profile"]
    assert child_info.source == ActionSource.MANUAL
    assert child_info.action == ActionType.USE  # Changed from ActionType.EXTENSION
    assert child_info.inherited_from is None
    assert child_info.user_remark == "Child override"


def test_incompatible_field_with_manual_action_is_manual():
    mapping = StubMapping([
        ("Observation.value", "incompatible"),
    ])
    manual_entries = {
        "Observation.value": {
            "action": "not_use",
            "remark": "Explicit decision",
        }
    }

    result = compute_mapping_actions(mapping, manual_entries)

    field_action = result["Observation.value"]
    assert field_action.action == ActionType.NOT_USE
    assert field_action.source == ActionSource.MANUAL
    assert field_action.user_remark == "Explicit decision"


def test_copy_from_entry_derives_partner_copy_to():
    mapping = StubMapping([
        "Medication.ingredient",
        "Medication.ingredient.reference",
    ])
    manual_entries = {
        "Medication.ingredient": {
            "action": "copy_from",
            "other": "Medication.ingredient.reference",
        }
    }

    result = compute_mapping_actions(mapping, manual_entries)

    source_info = result["Medication.ingredient"]
    partner_info = result["Medication.ingredient.reference"]

    assert source_info.action == ActionType.COPY_FROM
    assert source_info.source == ActionSource.MANUAL
    assert partner_info.action == ActionType.COPY_TO
    assert partner_info.source == ActionSource.MANUAL
    assert partner_info.other_value == "Medication.ingredient"


# ========================================
# Tests for compute_recommendations
# ========================================

def test_compatible_field_gets_recommendation():
    """Compatible fields without manual actions should get a USE recommendation."""
    mapping = StubMapping([("Observation.code", "compatible")])
    
    result = compute_recommendations(mapping, manual_entries={})
    
    assert "Observation.code" in result
    recommendations = result["Observation.code"]
    assert len(recommendations) == 1
    assert recommendations[0].action == ActionType.USE
    assert recommendations[0].source == ActionSource.SYSTEM_DEFAULT
    assert recommendations[0].auto_generated is True


def test_incompatible_field_gets_no_recommendation():
    """Incompatible fields should not get recommendations."""
    mapping = StubMapping([("Observation.value", "incompatible")])
    
    result = compute_recommendations(mapping, manual_entries={})
    
    # Incompatible fields should not have recommendations
    assert "Observation.value" not in result or len(result.get("Observation.value", [])) == 0


def test_field_with_manual_action_gets_no_recommendation():
    """Fields with manual actions should not get recommendations."""
    mapping = StubMapping([("Observation.code", "compatible")])
    manual_entries = {
        "Observation.code": {"action": "use"}
    }
    
    result = compute_recommendations(mapping, manual_entries)
    
    # Field has manual action, so no recommendation
    assert "Observation.code" not in result or len(result.get("Observation.code", [])) == 0


def test_multiple_compatible_fields_get_recommendations():
    """Multiple compatible fields should each get their own recommendations."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "compatible"),
        ("Patient.gender", "incompatible"),
    ])
    
    result = compute_recommendations(mapping, manual_entries={})
    
    # Two compatible fields should have recommendations
    assert "Patient.name" in result
    assert len(result["Patient.name"]) == 1
    assert result["Patient.name"][0].action == ActionType.USE
    
    assert "Patient.birthDate" in result
    assert len(result["Patient.birthDate"]) == 1
    assert result["Patient.birthDate"][0].action == ActionType.USE
    
    # Incompatible field should not have recommendation
    assert "Patient.gender" not in result or len(result.get("Patient.gender", [])) == 0


def test_recommendations_are_separate_from_actions():
    """Recommendations should not affect action computation.
    
    Note: Compatible fields without manual actions now get None action (not USE).
    They receive USE recommendations instead, which must be explicitly applied.
    """
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])
    manual_entries = {
        "Patient.name": {"action": "not_use"}
    }
    
    # Compute actions
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Compute recommendations
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Patient.name has manual action NOT_USE
    assert actions["Patient.name"].action == ActionType.NOT_USE
    
    # Patient.name should NOT have a recommendation (has manual action)
    assert "Patient.name" not in recommendations or len(recommendations.get("Patient.name", [])) == 0
    
    # Patient.birthDate has no manual action, so it gets None action (changed behavior)
    assert actions["Patient.birthDate"].action is None
    
    # Patient.birthDate should have a recommendation (no manual action + compatible)
    assert "Patient.birthDate" in recommendations
    assert len(recommendations["Patient.birthDate"]) == 1
