"""Tests for copy_node_to action inheritance and recommendations."""

from typing import Dict

from structure_comparer.mapping_actions_engine import (
    compute_mapping_actions,
    compute_recommendations,
)
from structure_comparer.mapping_evaluation_engine import evaluate_mapping
from structure_comparer.model.mapping_action_models import (
    ActionSource,
    ActionType,
    MappingStatus,
)


class StubField:
    def __init__(self, name: str, classification: str = "compatible"):
        self.name = name
        self.classification = classification
        self.is_target_required = False


class StubMapping:
    def __init__(self, field_defs):
        self.fields: Dict[str, StubField] = {}
        for definition in field_defs:
            if isinstance(definition, tuple):
                name, classification = definition
            else:
                name, classification = definition, "compatible"
            self.fields[name] = StubField(name, classification)


def test_parent_extension_action_marked_as_solved():
    """Test that parent field with extension action is marked as SOLVED."""
    mapping = StubMapping([
        ("Organization.address:Strassenanschrift.line.extension", "incompatible"),
        "Organization.address:Strassenanschrift.line.extension:Hausnummer",
        # Target fields
        "Organization.address.line",
        "Organization.address.line.extension:Hausnummer",
    ])
    
    manual_entries = {
        "Organization.address:Strassenanschrift.line.extension": {
            "action": "copy_node_to",
            "other": "Organization.address.line",
        }
    }
    
    # Get actions
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Evaluate mapping
    evaluations = evaluate_mapping(mapping, actions)
    
    # Parent should have manual copy_node_to action
    parent_field = "Organization.address:Strassenanschrift.line.extension"
    assert actions[parent_field].action == ActionType.COPY_NODE_TO
    assert actions[parent_field].source == ActionSource.MANUAL
    assert actions[parent_field].other_value == "Organization.address.line"
    
    # Parent should be marked as SOLVED
    assert evaluations[parent_field].mapping_status == MappingStatus.SOLVED


def test_parent_extension_creates_child_recommendation():
    """Test that parent extension creates recommendations for child fields."""
    mapping = StubMapping([
        "Organization.address:Strassenanschrift.line.extension",
        "Organization.address:Strassenanschrift.line.extension:Hausnummer",
        "Organization.address:Strassenanschrift.line.extension:Strasse",
        # Target fields must also exist for inheritance to work
        # Parent maps: .extension -> .line
        # So children should map: .extension:X -> .line:X
        "Organization.address.line",
        "Organization.address.line:Hausnummer",
        "Organization.address.line:Strasse",
    ])
    
    manual_entries = {
        "Organization.address:Strassenanschrift.line.extension": {
            "action": "copy_node_to",
            "other": "Organization.address.line",
        }
    }
    
    # Get actions
    actions = compute_mapping_actions(mapping, manual_entries)
    
    # Get recommendations
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Parent should have manual copy_node_to action
    parent_field = "Organization.address:Strassenanschrift.line.extension"
    assert actions[parent_field].action == ActionType.COPY_NODE_TO
    assert actions[parent_field].source == ActionSource.MANUAL
    
    # Parent should NOT have recommendations (has manual action)
    assert parent_field not in recommendations
    
    # Children should have recommendations (not active actions)
    child_field = "Organization.address:Strassenanschrift.line.extension:Hausnummer"
    assert child_field in recommendations
    child_recs = recommendations[child_field]
    assert len(child_recs) >= 1
    
    # Find the inherited copy_node_to recommendation
    inherited_rec = next(
        (r for r in child_recs if r.action == ActionType.COPY_NODE_TO), None
    )
    assert inherited_rec is not None
    # Parent maps .extension -> .line, so child should map .extension:Hausnummer -> .line:Hausnummer
    assert inherited_rec.other_value == "Organization.address.line:Hausnummer"
    assert inherited_rec.auto_generated is True
    
    # Children should NOT have active inherited actions
    child_action = actions[child_field]
    assert child_action.action is None  # No active action, only recommendation


def test_multiple_children_get_extension_recommendations():
    """Test that all children get extension recommendations with correct other_value."""
    mapping = StubMapping([
        "Medication.extension:A",
        "Medication.extension:A.url",
        "Medication.extension:A.value[x]",
        "Medication.extension:A.id",
        # Target fields
        "Medication.extension:B",
        "Medication.extension:B.url",
        "Medication.extension:B.value[x]",
        "Medication.extension:B.id",
    ])
    
    manual_entries = {
        "Medication.extension:A": {
            "action": "copy_node_to",
            "other": "Medication.extension:B",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # All children should have copy_node_to recommendations
    expected_children = [
        ("Medication.extension:A.url", "Medication.extension:B.url"),
        ("Medication.extension:A.value[x]", "Medication.extension:B.value[x]"),
        ("Medication.extension:A.id", "Medication.extension:B.id"),
    ]
    
    for child_field, expected_other in expected_children:
        assert child_field in recommendations, f"{child_field} should have recommendation"
        child_recs = recommendations[child_field]
        
        extension_rec = next(
            (r for r in child_recs if r.action == ActionType.COPY_NODE_TO), None
        )
        assert extension_rec is not None, f"{child_field} should have COPY_NODE_TO recommendation"
        assert extension_rec.other_value == expected_other, (
            f"{child_field} should have other_value={expected_other}, "
            f"got {extension_rec.other_value}"
        )


def test_child_with_manual_action_no_extension_recommendation():
    """Test that children with manual actions don't get copy_node_to recommendations."""
    mapping = StubMapping([
        "Patient.extension:A",
        "Patient.extension:A.url",
        "Patient.extension:B",
        "Patient.extension:B.url",
    ])
    
    manual_entries = {
        "Patient.extension:A": {
            "action": "copy_node_to",
            "other": "Patient.extension:B",
        },
        "Patient.extension:A.url": {
            "action": "fixed",
            "fixed": "http://example.com",
        },
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Child with manual action should NOT have recommendation
    assert "Patient.extension:A.url" not in recommendations


def test_extension_action_is_inheritable():
    """Test that COPY_NODE_TO is recognized as an inheritable action."""
    from structure_comparer.inheritance_engine import InheritanceEngine
    from structure_comparer.model.mapping_action_models import ActionType
    
    engine = InheritanceEngine({})
    
    # COPY_NODE_TO should be inheritable
    assert engine.can_inherit_action(ActionType.COPY_NODE_TO)
    
    # COPY_NODE_TO should be treated as a copy action
    assert engine.is_copy_action(ActionType.COPY_NODE_TO)


def test_extension_in_inheritable_actions():
    """Test that COPY_NODE_TO is in _INHERITABLE_ACTIONS."""
    from structure_comparer.mapping_actions_engine import _INHERITABLE_ACTIONS
    from structure_comparer.model.mapping_action_models import ActionType
    
    assert ActionType.COPY_NODE_TO in _INHERITABLE_ACTIONS
