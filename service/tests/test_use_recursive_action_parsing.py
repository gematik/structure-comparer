"""Test that USE_RECURSIVE action is correctly parsed from manual entries.

This test verifies the fix for the bug where applying a USE_RECURSIVE recommendation
would result in the parent field showing only "use" instead of "use_recursive".

The root cause was that _parse_action didn't handle Action enum values,
only ActionType and string values.
"""

from structure_comparer.action import Action
from structure_comparer.mapping_actions_engine import compute_mapping_actions
from structure_comparer.model.mapping_action_models import ActionSource, ActionType


class StubField:
    def __init__(self, name: str, classification: str = "compatible"):
        self.name = name
        self.classification = classification


class StubMapping:
    def __init__(self, field_defs):
        self.fields = {}
        for definition in field_defs:
            if isinstance(definition, tuple):
                name, classification = definition
            else:
                name, classification = definition, "compatible"
            self.fields[name] = StubField(name, classification)


def test_parse_action_enum_use_recursive():
    """Test that Action.USE_RECURSIVE is correctly parsed."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.name.given", "compatible"),
    ])
    
    # Manual entry with Action enum (as written by apply_recommendation)
    manual_entries = {
        "Patient.name": {
            "name": "Patient.name",
            "action": Action.USE_RECURSIVE,  # This is an Action enum, not string!
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Parent should have USE_RECURSIVE action
    parent_action = actions.get("Patient.name")
    assert parent_action is not None, "Parent action should exist"
    assert parent_action.action == ActionType.USE_RECURSIVE, \
        f"Expected USE_RECURSIVE, got {parent_action.action}"
    assert parent_action.source == ActionSource.MANUAL, \
        f"Expected MANUAL source, got {parent_action.source}"
    
    # Child should inherit USE_RECURSIVE
    child_action = actions.get("Patient.name.given")
    assert child_action is not None, "Child action should exist"
    assert child_action.action == ActionType.USE_RECURSIVE, \
        f"Expected inherited USE_RECURSIVE, got {child_action.action}"
    assert child_action.source == ActionSource.INHERITED, \
        f"Expected INHERITED source, got {child_action.source}"
    assert child_action.inherited_from == "Patient.name", \
        f"Expected inherited from Patient.name, got {child_action.inherited_from}"


def test_parse_action_string_use_recursive():
    """Test that 'use_recursive' string is correctly parsed."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.name.given", "compatible"),
    ])
    
    # Manual entry with string value (as written to YAML)
    manual_entries = {
        "Patient.name": {
            "name": "Patient.name",
            "action": "use_recursive",  # String value
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Parent should have USE_RECURSIVE action
    parent_action = actions.get("Patient.name")
    assert parent_action is not None, "Parent action should exist"
    assert parent_action.action == ActionType.USE_RECURSIVE, \
        f"Expected USE_RECURSIVE, got {parent_action.action}"
    
    # Child should inherit USE_RECURSIVE
    child_action = actions.get("Patient.name.given")
    assert child_action is not None, "Child action should exist"
    assert child_action.action == ActionType.USE_RECURSIVE, \
        f"Expected inherited USE_RECURSIVE, got {child_action.action}"


def test_parse_action_actiontype_use_recursive():
    """Test that ActionType.USE_RECURSIVE is correctly parsed."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.name.given", "compatible"),
    ])
    
    # Manual entry with ActionType enum
    manual_entries = {
        "Patient.name": {
            "name": "Patient.name",
            "action": ActionType.USE_RECURSIVE,  # ActionType enum
        }
    }
    
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Parent should have USE_RECURSIVE action
    parent_action = actions.get("Patient.name")
    assert parent_action is not None, "Parent action should exist"
    assert parent_action.action == ActionType.USE_RECURSIVE, \
        f"Expected USE_RECURSIVE, got {parent_action.action}"
    
    # Child should inherit USE_RECURSIVE
    child_action = actions.get("Patient.name.given")
    assert child_action is not None, "Child action should exist"
    assert child_action.action == ActionType.USE_RECURSIVE, \
        f"Expected inherited USE_RECURSIVE, got {child_action.action}"


def test_all_action_enum_values_are_parsed():
    """Test that all Action enum values can be parsed."""
    from structure_comparer.mapping_actions_engine import _parse_action
    
    for action in Action:
        parsed = _parse_action(action)
        assert parsed is not None, f"Failed to parse Action.{action.name}"
        assert parsed.value == action.value, \
            f"Parsed value mismatch for Action.{action.name}: {parsed.value} != {action.value}"


if __name__ == "__main__":
    test_parse_action_enum_use_recursive()
    test_parse_action_string_use_recursive()
    test_parse_action_actiontype_use_recursive()
    test_all_action_enum_values_are_parsed()
    print("✅ All tests passed!")
