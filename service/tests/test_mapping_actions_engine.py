from typing import Dict

from structure_comparer.mapping_actions_engine import compute_mapping_actions
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
)


class StubField:
    def __init__(self, name: str):
        self.name = name


class StubMapping:
    def __init__(self, field_names):
        self.fields: Dict[str, StubField] = {
            name: StubField(name) for name in field_names
        }


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


def test_manual_child_action_prevents_inheritance():
    mapping = StubMapping([
        "Practitioner.meta",
        "Practitioner.meta.profile",
    ])
    manual_entries = {
        "Practitioner.meta": {"action": "not_use"},
        "Practitioner.meta.profile": {
            "action": "use",
            "remark": "Child override",
        },
    }

    result = compute_mapping_actions(mapping, manual_entries)

    child_info = result["Practitioner.meta.profile"]
    assert child_info.source == ActionSource.MANUAL
    assert child_info.action == ActionType.USE
    assert child_info.inherited_from is None
    assert child_info.user_remark == "Child override"
