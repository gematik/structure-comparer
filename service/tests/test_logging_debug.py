"""Debug test to check why recommendations are not created."""

import logging
from typing import Dict

from structure_comparer.mapping_actions_engine import (
    compute_mapping_actions,
    compute_recommendations,
)
from structure_comparer.model.mapping_action_models import (
    ActionSource,
    ActionType,
)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')


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
                fname, classification = name
                self.fields[fname] = StubField(fname, classification)
            else:
                self.fields[name] = StubField(name)
        self.target = None


def test_practitioner_identifier_copy_to():
    """Test the exact case from the user: Practitioner.identifier:ANR -> LANR."""
    
    print("\n" + "="*80)
    print("TEST: Practitioner.identifier:ANR COPY_TO Practitioner.identifier:LANR")
    print("="*80 + "\n")
    
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.id",
        "Practitioner.identifier:ANR.extension",
        "Practitioner.identifier:ANR.use",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:ANR.value",
        "Practitioner.identifier:LANR",
        "Practitioner.identifier:LANR.id",
        "Practitioner.identifier:LANR.extension",
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
    
    print("Computing actions...")
    actions = compute_mapping_actions(mapping, manual_entries)
    
    print("\nComputing recommendations...")
    recommendations = compute_recommendations(mapping, manual_entries)
    
    print("\n" + "="*80)
    print("RESULTS:")
    print("="*80)
    
    print(f"\nParent action: {actions['Practitioner.identifier:ANR'].action}")
    print(f"Parent source: {actions['Practitioner.identifier:ANR'].source}")
    print(f"Parent other_value: {actions['Practitioner.identifier:ANR'].other_value}")
    
    print("\nChild fields:")
    for child_name in [
        "Practitioner.identifier:ANR.id",
        "Practitioner.identifier:ANR.extension",
        "Practitioner.identifier:ANR.use",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:ANR.value",
    ]:
        print(f"\n  {child_name}:")
        child_action = actions.get(child_name)
        print(f"    Action: {child_action.action if child_action else 'N/A'}")
        
        # Get field from mapping to check actions_allowed
        field = mapping.fields.get(child_name)
        if field:
            print(f"    Actions allowed: {field.actions_allowed}")
        
        if child_name in recommendations:
            print(f"    Recommendations: {len(recommendations[child_name])}")
            for rec in recommendations[child_name]:
                print(f"      - {rec.action.value} -> {rec.other_value}")
                if field and field.actions_allowed:
                    allowed_values = [
                        a.value if hasattr(a, 'value') else a
                        for a in field.actions_allowed
                    ]
                    is_allowed = rec.action.value in allowed_values
                    print(f"        Allowed by field? {is_allowed}")
        else:
            print("    Recommendations: NONE ❌")
    
    # Assertions
    assert "Practitioner.identifier:ANR.id" in recommendations, \
        "Expected recommendation for .id field"
    assert "Practitioner.identifier:ANR.extension" in recommendations, \
        "Expected recommendation for .extension field"


if __name__ == "__main__":
    test_practitioner_identifier_copy_to()
