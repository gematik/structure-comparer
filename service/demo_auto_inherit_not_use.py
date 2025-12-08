#!/usr/bin/env python3
"""Demo script to demonstrate the auto-inherit NOT_USE feature.

This script shows how when a parent field has NOT_USE with source=MANUAL,
all direct children automatically receive NOT_USE with source=INHERITED.
"""

from src.structure_comparer.mapping_actions_engine import compute_mapping_actions
from src.structure_comparer.model.mapping_action_models import ActionSource, ActionType


class MockField:
    """Mock field object for demonstration."""

    def __init__(self, name: str, classification: str = "unknown"):
        self.name = name
        self.classification = classification
        self.profiles = {}
        self.actions_allowed = []


class MockMapping:
    """Mock mapping object for demonstration."""

    def __init__(self, fields: dict):
        self.fields = fields
        self.target = None


def demo():
    """Demonstrate the auto-inherit NOT_USE feature."""
    print("=" * 80)
    print("AUTO-INHERIT NOT_USE FEATURE DEMONSTRATION")
    print("=" * 80)
    print()

    # Create a field hierarchy
    fields = {
        "Patient.identifier": MockField("Patient.identifier"),
        "Patient.identifier.system": MockField("Patient.identifier.system"),
        "Patient.identifier.value": MockField("Patient.identifier.value"),
        "Patient.identifier.use": MockField("Patient.identifier.use"),
        "Patient.identifier.type": MockField("Patient.identifier.type"),
        "Patient.identifier.type.coding": MockField("Patient.identifier.type.coding"),
    }

    mapping = MockMapping(fields)

    # Manual entry: Set NOT_USE on Patient.identifier
    manual_entries = {
        "Patient.identifier": {
            "action": "not_use",
            "remark": "Not needed in this profile",
        }
    }

    print("Manual Entry:")
    print("-" * 80)
    print(f"  Patient.identifier: action=not_use, remark='Not needed in this profile'")
    print()

    # Compute mapping actions
    result = compute_mapping_actions(mapping, manual_entries)

    print("Computed Actions:")
    print("-" * 80)

    # Show parent
    parent = result["Patient.identifier"]
    print(f"✓ Patient.identifier:")
    print(f"    action: {parent.action}")
    print(f"    source: {parent.source}")
    print(f"    remark: {parent.user_remark}")
    print()

    # Show direct children (should have inherited NOT_USE)
    print("Direct Children (automatically inherit NOT_USE):")
    direct_children = [
        "Patient.identifier.system",
        "Patient.identifier.value",
        "Patient.identifier.use",
        "Patient.identifier.type",
    ]

    for child_name in direct_children:
        child = result[child_name]
        print(f"  ✓ {child_name}:")
        print(f"      action: {child.action}")
        print(f"      source: {child.source}")
        print(f"      inherited_from: {child.inherited_from}")
        print(f"      system_remark: {child.system_remark}")
        print()

    # Show grandchild (should NOT have inherited NOT_USE from grandparent)
    print("Grandchild (does NOT inherit from grandparent):")
    grandchild = result["Patient.identifier.type.coding"]
    print(f"  ✗ Patient.identifier.type.coding:")
    print(f"      action: {grandchild.action}")
    print(f"      source: {grandchild.source}")
    print(
        f"      Note: No automatic inheritance because parent has source=INHERITED, not MANUAL"
    )
    print()

    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print("  - Parent with NOT_USE (MANUAL) → Direct children get NOT_USE (INHERITED)")
    print("  - Grandchildren do NOT automatically inherit (parent is INHERITED, not MANUAL)")
    print("  - Manual actions on children are never overridden")


if __name__ == "__main__":
    demo()
