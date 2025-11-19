from typing import Dict

from structure_comparer.mapping_actions_engine import compute_mapping_actions
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
    mapping = StubMapping([
        "Patient.identifier",
        "Patient.identifier.system",
    ])
    manual_entries = {
        "Patient.identifier": {
            "action": "not_use",
        }
    }

    result = compute_mapping_actions(mapping, manual_entries)

    parent_info = result["Patient.identifier"]
    child_info = result["Patient.identifier.system"]

    assert parent_info.action == ActionType.NOT_USE
    assert parent_info.source == ActionSource.MANUAL

    assert child_info.action == ActionType.NOT_USE
    assert child_info.source == ActionSource.INHERITED
    assert child_info.inherited_from == "Patient.identifier"
    assert child_info.auto_generated is True


def test_system_default_action_fills_missing_entries():
    mapping = StubMapping(["Observation.code"])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.code"]
    assert field_action.action == ActionType.USE
    assert field_action.source == ActionSource.SYSTEM_DEFAULT
    assert field_action.auto_generated is True


def test_incompatible_field_without_manual_action_has_no_use_default():
    mapping = StubMapping([
        ("Observation.value", "incompatible"),
    ])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.value"]
    assert field_action.action == ActionType.OTHER
    assert field_action.source == ActionSource.SYSTEM_DEFAULT
    assert field_action.auto_generated is True


def test_warning_field_without_manual_action_has_no_use_default():
    mapping = StubMapping([
        ("Observation.note", "warning"),
    ])

    result = compute_mapping_actions(mapping, manual_entries={})

    field_action = result["Observation.note"]
    assert field_action.action == ActionType.OTHER
    assert field_action.source == ActionSource.SYSTEM_DEFAULT


def test_manual_child_action_prevents_inheritance():
    mapping = StubMapping([
        "Practitioner.meta",
        "Practitioner.meta.profile",
    ])
    manual_entries = {
        "Practitioner.meta": {"action": "not_use"},
        "Practitioner.meta.profile": {
            "action": "extension",
            "remark": "Child override",
        },
    }

    result = compute_mapping_actions(mapping, manual_entries)

    child_info = result["Practitioner.meta.profile"]
    assert child_info.source == ActionSource.MANUAL
    assert child_info.action == ActionType.EXTENSION
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
