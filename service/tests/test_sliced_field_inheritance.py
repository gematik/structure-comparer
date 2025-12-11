"""Tests for greedy inheritance with sliced fields (realistic FHIR scenario)."""

from typing import Dict

from structure_comparer.mapping_actions_engine import compute_recommendations
from structure_comparer.model.mapping_action_models import ActionType


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


def test_sliced_identifier_with_base_field_fallback():
    """Test realistic FHIR scenario: identifier:ANR -> identifier:LANR
    
    In FHIR StructureDefinitions, slices like identifier:LANR often don't have
    explicit child fields listed. Instead, they inherit from the base Identifier type.
    
    The mapping should create recommendations even when target slice children
    don't exist explicitly, as long as the base field children exist.
    """
    
    mapping = StubMapping([
        # Source slice with all children
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.id",
        "Practitioner.identifier:ANR.extension",
        "Practitioner.identifier:ANR.use",
        "Practitioner.identifier:ANR.system",
        "Practitioner.identifier:ANR.value",
        
        # Target slice WITHOUT explicit children (realistic!)
        "Practitioner.identifier:LANR",
        # Note: NO Practitioner.identifier:LANR.id, etc.
        
        # Base identifier field with children (from Identifier type)
        "Practitioner.identifier",
        "Practitioner.identifier.id",
        "Practitioner.identifier.extension",
        "Practitioner.identifier.use",
        "Practitioner.identifier.system",
        "Practitioner.identifier.value",
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_value_to",
            "other": "Practitioner.identifier:LANR",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # All ANR children should get recommendations
    # Even though LANR.id doesn't exist, Practitioner.identifier.id does (fallback)
    assert "Practitioner.identifier:ANR.id" in recommendations
    id_recs = recommendations["Practitioner.identifier:ANR.id"]
    copy_value_to_rec = next((r for r in id_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Practitioner.identifier:LANR.id"
    
    assert "Practitioner.identifier:ANR.system" in recommendations
    system_recs = recommendations["Practitioner.identifier:ANR.system"]
    copy_value_to_rec = next((r for r in system_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Practitioner.identifier:LANR.system"
    
    assert "Practitioner.identifier:ANR.value" in recommendations
    value_recs = recommendations["Practitioner.identifier:ANR.value"]
    copy_value_to_rec = next((r for r in value_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Practitioner.identifier:LANR.value"


def test_no_fallback_when_base_field_also_missing():
    """Test that recommendations are created for sliced custom fields (implicit slice).
    
    Even if a custom field doesn't exist in the base type, if it exists in the source slice,
    it should create a recommendation for the target slice (structurally valid).
    """
    
    mapping = StubMapping([
        "Practitioner.identifier:ANR",
        "Practitioner.identifier:ANR.customField",  # Custom field not in base type
        
        "Practitioner.identifier:LANR",
        # No LANR.customField (but structurally valid since source has it)
        
        "Practitioner.identifier",
        # No identifier.customField in base type either
    ])
    
    manual_entries = {
        "Practitioner.identifier:ANR": {
            "action": "copy_value_to",
            "other": "Practitioner.identifier:LANR",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # SHOULD create recommendation for customField (implicit slice - source has it)
    assert "Practitioner.identifier:ANR.customField" in recommendations
    custom_recs = recommendations["Practitioner.identifier:ANR.customField"]
    copy_value_to_rec = next((r for r in custom_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Practitioner.identifier:LANR.customField"
    # Check that the remarks indicate it's an implicit slice
    assert copy_value_to_rec.system_remarks is not None
    assert any("not explicitly defined" in remark for remark in copy_value_to_rec.system_remarks)


def test_non_sliced_fields_not_affected_by_fallback():
    """Test that non-sliced fields still work correctly (no regression)."""
    
    mapping = StubMapping([
        "Medication.code",
        "Medication.code.coding",
        "Medication.code.coding.system",
        "Medication.code.text",
        
        "Medication.ingredient",
        "Medication.ingredient.coding",  # Must exist for recommendation
        "Medication.ingredient.coding.system",
        "Medication.ingredient.text",
    ])
    
    manual_entries = {
        "Medication.code": {
            "action": "copy_value_to",
            "other": "Medication.ingredient",
        }
    }
    
    recommendations = compute_recommendations(mapping, manual_entries)
    
    # Should create recommendations for children
    assert "Medication.code.coding" in recommendations
    coding_recs = recommendations["Medication.code.coding"]
    copy_value_to_rec = next((r for r in coding_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Medication.ingredient.coding"
    
    # Check nested child too
    assert "Medication.code.coding.system" in recommendations
    system_recs = recommendations["Medication.code.coding.system"]
    copy_value_to_rec = next((r for r in system_recs if r.action == ActionType.COPY_VALUE_TO), None)
    assert copy_value_to_rec is not None
    assert copy_value_to_rec.other_value == "Medication.ingredient.coding.system"
