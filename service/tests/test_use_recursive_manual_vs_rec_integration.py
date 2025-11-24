"""Integration test comparing MANUAL vs RECOMMENDATION paths for USE_RECURSIVE.

This test ensures that:
1. Manually setting USE_RECURSIVE on a parent field works correctly
2. Applying a USE_RECURSIVE recommendation works identically
3. Both paths result in the same actions for parent and children
"""

from structure_comparer.action import Action
from structure_comparer.mapping_actions_engine import compute_mapping_actions
from structure_comparer.model.mapping import MappingFieldBase
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


class MockManualEntries:
    """Mock manual entries that behaves like the real ManualEntries object."""
    
    def __init__(self):
        self._entries = {}
    
    def get(self, mapping_id):
        """Return a mock mapping object."""
        return self
    
    def __setitem__(self, field_name, value):
        """Store a manual entry."""
        if isinstance(value, MappingFieldBase):
            # Convert to dict representation
            self._entries[field_name] = {
                "name": value.name,
                "action": value.action,  # This will be an Action enum!
                "other": value.other,
                "fixed": value.fixed,
                "remark": value.remark,
            }
        else:
            self._entries[field_name] = value
    
    def __contains__(self, field_name):
        return field_name in self._entries
    
    def items(self):
        return self._entries.items()
    
    @property
    def fields(self):
        """Return list of field entries."""
        return [
            {"name": name, **data}
            for name, data in self._entries.items()
        ]


def test_manual_vs_recommendation_use_recursive():
    """Compare MANUAL setting vs RECOMMENDATION apply for USE_RECURSIVE.
    
    This is the core test that verifies the fix for the reported bug.
    """
    # Setup: Mapping with parent and children
    mapping = StubMapping([
        ("Medication.ingredient", "compatible"),
        ("Medication.ingredient.item", "compatible"),
        ("Medication.ingredient.strength", "compatible"),
    ])
    
    print("\n" + "="*80)
    print("SCENARIO A: MANUAL PATH - Directly set USE_RECURSIVE")
    print("="*80)
    
    # MANUAL PATH: User manually sets USE_RECURSIVE
    manual_entries_a = {
        "Medication.ingredient": {
            "name": "Medication.ingredient",
            "action": Action.USE_RECURSIVE,  # Action enum from action.py
        }
    }
    
    actions_a = compute_mapping_actions(mapping, manual_entries_a)
    
    parent_a = actions_a.get("Medication.ingredient")
    child1_a = actions_a.get("Medication.ingredient.item")
    child2_a = actions_a.get("Medication.ingredient.strength")
    
    print(f"Parent action: {parent_a.action if parent_a else None}")
    print(f"  Source: {parent_a.source if parent_a else None}")
    print(f"Child 1 action: {child1_a.action if child1_a else None}")
    print(f"  Source: {child1_a.source if child1_a else None}")
    print(f"  Inherited from: {child1_a.inherited_from if child1_a else None}")
    print(f"Child 2 action: {child2_a.action if child2_a else None}")
    print(f"  Source: {child2_a.source if child2_a else None}")
    print(f"  Inherited from: {child2_a.inherited_from if child2_a else None}")
    
    print("\n" + "="*80)
    print("SCENARIO B: RECOMMENDATION PATH - Apply recommendation")
    print("="*80)
    
    # RECOMMENDATION PATH: Simulate what apply_recommendation does
    # 1. Create MappingFieldBase with Action.USE_RECURSIVE
    # 2. Store it in manual_entries (this is what the handler does)
    mock_manual_entries = MockManualEntries()
    mock_manual_entries["Medication.ingredient"] = MappingFieldBase(
        name="Medication.ingredient",
        action=Action.USE_RECURSIVE,  # This is what apply_recommendation writes!
    )
    
    # 3. Compute actions (this is what fill_action_remark does)
    actions_b = compute_mapping_actions(mapping, mock_manual_entries)
    
    parent_b = actions_b.get("Medication.ingredient")
    child1_b = actions_b.get("Medication.ingredient.item")
    child2_b = actions_b.get("Medication.ingredient.strength")
    
    print(f"Parent action: {parent_b.action if parent_b else None}")
    print(f"  Source: {parent_b.source if parent_b else None}")
    print(f"Child 1 action: {child1_b.action if child1_b else None}")
    print(f"  Source: {child1_b.source if child1_b else None}")
    print(f"  Inherited from: {child1_b.inherited_from if child1_b else None}")
    print(f"Child 2 action: {child2_b.action if child2_b else None}")
    print(f"  Source: {child2_b.source if child2_b else None}")
    print(f"  Inherited from: {child2_b.inherited_from if child2_b else None}")
    
    print("\n" + "="*80)
    print("COMPARISON")
    print("="*80)
    
    # Compare parent actions
    print(f"Parent action matches: {parent_a.action == parent_b.action}")
    assert parent_a.action == ActionType.USE_RECURSIVE, \
        f"Manual path: Expected USE_RECURSIVE, got {parent_a.action}"
    assert parent_b.action == ActionType.USE_RECURSIVE, \
        f"Recommendation path: Expected USE_RECURSIVE, got {parent_b.action}"
    assert parent_a.action == parent_b.action, \
        "Parent actions must be identical!"
    
    # Compare child actions
    print(f"Child 1 action matches: {child1_a.action == child1_b.action}")
    assert child1_a.action == ActionType.USE_RECURSIVE, \
        f"Manual path child 1: Expected inherited USE_RECURSIVE, got {child1_a.action}"
    assert child1_b.action == ActionType.USE_RECURSIVE, \
        f"Recommendation path child 1: Expected inherited USE_RECURSIVE, got {child1_b.action}"
    assert child1_a.action == child1_b.action, \
        "Child 1 actions must be identical!"
    
    print(f"Child 2 action matches: {child2_a.action == child2_b.action}")
    assert child2_a.action == ActionType.USE_RECURSIVE, \
        f"Manual path child 2: Expected inherited USE_RECURSIVE, got {child2_a.action}"
    assert child2_b.action == ActionType.USE_RECURSIVE, \
        f"Recommendation path child 2: Expected inherited USE_RECURSIVE, got {child2_b.action}"
    assert child2_a.action == child2_b.action, \
        "Child 2 actions must be identical!"
    
    # Compare sources
    assert parent_a.source == parent_b.source == ActionSource.MANUAL
    assert child1_a.source == child1_b.source == ActionSource.INHERITED
    assert child2_a.source == child2_b.source == ActionSource.INHERITED
    
    print("\n✅ SUCCESS: Both paths produce IDENTICAL results!")
    print("   - Parent has USE_RECURSIVE action")
    print("   - Children correctly inherit USE_RECURSIVE")


if __name__ == "__main__":
    test_manual_vs_recommendation_use_recursive()
