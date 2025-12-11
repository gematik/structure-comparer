"""
Test cases for manual_entries_migration module.
"""

import pytest
from structure_comparer.manual_entries_migration import migrate_manual_entries


def test_migrate_new_format_unchanged():
    """Test that new format data is returned unchanged."""
    new_format_data = {
        "entries": [
            {
                "id": "test-mapping-123",
                "fields": [
                    {
                        "name": "test.field",
                        "action": "FIXED",
                        "fixed": "test value"
                    }
                ]
            }
        ]
    }
    
    result = migrate_manual_entries(new_format_data)
    assert result == new_format_data


def test_migrate_legacy_format():
    """Test migration of legacy format to new format."""
    legacy_data = {
        "0760ae49-8551-459b-bc65-39bfb47697f8": {
            "MedicationRequest.dosageInstruction.extension:Dosierungskennzeichen": {
                "classification": "not_use"
            },
            "MedicationRequest.extension:Mehrfachverordnung": {
                "classification": "copy_from",
                "extra": "MedicationRequest.extension:multiplePrescription"
            },
            "MedicationRequest.intent": {
                "classification": "fixed",
                "extra": "filler-order"
            },
            "MedicationRequest.identifier:rxPrescriptionProcessIdentifier": {
                "classification": "empty",
                "remark": "Dieser Identifier wird vom Medication Service vergeben."
            }
        }
    }
    
    result = migrate_manual_entries(legacy_data)
    
    # Verify structure
    assert "entries" in result
    assert len(result["entries"]) == 1
    
    entry = result["entries"][0]
    assert entry["id"] == "0760ae49-8551-459b-bc65-39bfb47697f8"
    assert len(entry["fields"]) == 4
    
    # Check specific field migrations
    fields_by_name = {f["name"]: f for f in entry["fields"]}
    
    # Test not_use classification
    not_use_field = fields_by_name["MedicationRequest.dosageInstruction.extension:Dosierungskennzeichen"]
    assert not_use_field["action"] == "not_use"
    
    # Test copy_value_from with extra -> other
    copy_value_from_field = fields_by_name["MedicationRequest.extension:Mehrfachverordnung"]
    assert copy_value_from_field["action"] == "copy_value_from"
    assert copy_value_from_field["other"] == "MedicationRequest.extension:multiplePrescription"
    
    # Test fixed with extra -> fixed
    fixed_field = fields_by_name["MedicationRequest.intent"]
    assert fixed_field["action"] == "fixed"
    assert fixed_field["fixed"] == "filler-order"
    
    # Test empty with remark
    empty_field = fields_by_name["MedicationRequest.identifier:rxPrescriptionProcessIdentifier"]
    assert empty_field["action"] == "empty"
    assert empty_field["remark"] == "Dieser Identifier wird vom Medication Service vergeben."


def test_migrate_all_classifications():
    """Test migration of all supported classifications."""
    legacy_data = {
        "test-mapping": {
            "field1": {"classification": "use"},
            "field2": {"classification": "not_use"},
            "field3": {"classification": "empty"},
            "field4": {"classification": "fixed", "extra": "fixed-value"},
            "field5": {"classification": "copy_from", "extra": "source.field"},
            "field6": {"classification": "copy_to", "extra": "target.field"},
            "field7": {"classification": "manual"},
            "field8": {"classification": "medication_service"},
        }
    }
    
    result = migrate_manual_entries(legacy_data)
    
    entry = result["entries"][0]
    fields_by_name = {f["name"]: f for f in entry["fields"]}
    
    assert fields_by_name["field1"]["action"] == "use"
    assert fields_by_name["field2"]["action"] == "not_use"
    assert fields_by_name["field3"]["action"] == "empty"
    assert fields_by_name["field4"]["action"] == "fixed"
    assert fields_by_name["field4"]["fixed"] == "fixed-value"
    assert fields_by_name["field5"]["action"] == "copy_value_from"
    assert fields_by_name["field5"]["other"] == "source.field"
    assert fields_by_name["field6"]["action"] == "copy_value_to"
    assert fields_by_name["field6"]["other"] == "target.field"
    assert fields_by_name["field7"]["action"] == "manual"
    # medication_service is now migrated to manual with default remark
    assert fields_by_name["field8"]["action"] == "manual"
    assert fields_by_name["field8"]["remark"] == "Property will be set by medication_service"


def test_migrate_empty_legacy_data():
    """Test migration of empty legacy data."""
    result = migrate_manual_entries({})
    assert result == {"entries": []}


def test_migrate_invalid_data():
    """Test error handling for invalid data."""
    # Test non-dict input
    with pytest.raises(ValueError, match="Legacy data must be a dictionary"):
        migrate_manual_entries("not a dict")
    
    # Test unknown classification - should be skipped, not raise error
    invalid_data = {
        "test-mapping": {
            "field1": {"classification": "unknown_action"}
        }
    }
    result = migrate_manual_entries(invalid_data)
    # Mapping with only invalid fields should be skipped
    assert result == {"entries": []}
    
    # Test missing classification
    missing_classification = {
        "test-mapping": {
            "field1": {"remark": "test"}
        }
    }
    result = migrate_manual_entries(missing_classification)
    # Mapping with only invalid fields should be skipped
    assert result == {"entries": []}


def test_migrate_partial_invalid_fields():
    """Test that valid fields are migrated even when some fields are invalid."""
    mixed_data = {
        "test-mapping": {
            "valid_field": {"classification": "use"},
            "invalid_field": {"remark": "no classification"},
            "another_valid": {"classification": "not_use"}
        }
    }
    
    result = migrate_manual_entries(mixed_data)
    
    # Should have migrated only the 2 valid fields
    entry = result["entries"][0]
    assert len(entry["fields"]) == 2
    
    field_names = [f["name"] for f in entry["fields"]]
    assert "valid_field" in field_names
    assert "another_valid" in field_names
    assert "invalid_field" not in field_names


if __name__ == "__main__":
    # Run some basic tests if executed directly
    print("Testing new format detection...")
    test_migrate_new_format_unchanged()
    print("✓ New format unchanged")
    
    print("Testing legacy format migration...")
    test_migrate_legacy_format()
    print("✓ Legacy format migrated")
    
    print("Testing all classifications...")
    test_migrate_all_classifications()
    print("✓ All classifications mapped")
    
    print("Testing error handling...")
    test_migrate_invalid_data()
    print("✓ Error handling works")
    
    print("All tests passed!")
