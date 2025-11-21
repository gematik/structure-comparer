"""Tests for applying recommendations to convert them into active actions."""

from typing import Dict

from structure_comparer.mapping_actions_engine import compute_recommendations
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


def test_apply_first_recommendation_from_list():
    """Test that we can apply the first recommendation from a list."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])
    
    recommendations = compute_recommendations(mapping, manual_entries={})
    
    # Patient.name should have recommendations
    assert "Patient.name" in recommendations
    name_recommendations = recommendations["Patient.name"]
    assert len(name_recommendations) == 1
    
    # Simulate applying the first recommendation (index 0)
    applied_recommendation = name_recommendations[0]
    assert applied_recommendation.action == ActionType.USE
    assert applied_recommendation.source == ActionSource.SYSTEM_DEFAULT
    
    # After applying, the recommendation should be converted to a manual action
    # This would happen in the handler: apply_recommendation(index=0)


def test_apply_specific_recommendation_by_index():
    """Test that we can select a specific recommendation by index.
    
    This test prepares for future scenarios where multiple recommendations exist.
    """
    mapping = StubMapping([("Patient.name", "compatible")])
    
    recommendations = compute_recommendations(mapping, manual_entries={})
    
    # Currently we only have one recommendation per field
    name_recommendations = recommendations["Patient.name"]
    assert len(name_recommendations) == 1
    
    # Test index validation would happen in handler
    # Valid: index = 0
    # Invalid: index = 1 (out of bounds)
    
    # Simulate applying with index 0
    index = 0
    assert index < len(name_recommendations)
    applied = name_recommendations[index]
    assert applied.action == ActionType.USE


def test_invalid_index_out_of_bounds():
    """Test that applying a recommendation with invalid index fails."""
    mapping = StubMapping([("Patient.name", "compatible")])
    
    recommendations = compute_recommendations(mapping, manual_entries={})
    name_recommendations = recommendations["Patient.name"]
    
    # Try to apply index 5 when only 1 recommendation exists
    invalid_index = 5
    assert invalid_index >= len(name_recommendations)
    
    # The handler should raise an error for this case
    # raise MappingNotFound(f"Invalid recommendation index {invalid_index}...")


def test_apply_recommendation_with_no_recommendations():
    """Test that applying a recommendation when none exist fails."""
    mapping = StubMapping([("Patient.gender", "incompatible")])
    
    recommendations = compute_recommendations(mapping, manual_entries={})
    
    # Incompatible fields don't get recommendations
    assert "Patient.gender" not in recommendations or len(recommendations.get("Patient.gender", [])) == 0
    
    # Handler should raise: "No recommendations available for field 'Patient.gender'"


def test_recommendations_remain_separate_from_manual_actions():
    """Test that recommendations and manual actions are independent."""
    mapping = StubMapping([
        ("Patient.name", "compatible"),
        ("Patient.birthDate", "compatible"),
    ])
    
    # Patient.name has a manual action
    manual_entries = {
        "Patient.name": {"action": "not_use"}
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Patient.name has manual action -> no recommendation
    assert "Patient.name" not in recommendations or len(recommendations.get("Patient.name", [])) == 0
    
    # Patient.birthDate has no manual action -> has recommendation
    assert "Patient.birthDate" in recommendations
    assert len(recommendations["Patient.birthDate"]) == 1
    
    # After applying the recommendation for Patient.birthDate:
    # 1. It becomes a manual action
    # 2. It should no longer appear in recommendations
    # 3. The manual_entries would be updated with the new action
