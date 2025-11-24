"""Integration tests for fixed value detection in mapping actions engine."""

import unittest
from unittest.mock import Mock

from structure_comparer.mapping_actions_engine import (
    compute_mapping_actions,
    _get_fixed_value_from_field,
)
from structure_comparer.model.mapping_action_models import ActionSource, ActionType


class TestFixedValueDetection(unittest.TestCase):
    """Test automatic detection of fixed values from StructureDefinitions."""

    def test_fixed_uri_detected_automatically(self):
        """Test that fixedUri values are automatically detected and set as FIXED action."""
        # Setup mock mapping with a field that has a fixedUri in target profile
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        # Create a field with fixedUri in target
        field = Mock()
        field.name = "Extension.url"
        field.classification = "compatible"
        field.actions_allowed = [ActionType.USE, ActionType.FIXED]
        
        # Create target profile field with fixed value
        target_field = Mock()
        target_field.fixed_value = "https://example.com/fhir/StructureDefinition/example-extension"
        target_field.fixed_value_type = "fixedUri"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            "target-profile|1.0.0": target_field
        }
        
        mapping.fields = {
            "Extension.url": field
        }
        
        # Compute actions
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        # Verify FIXED action was set automatically
        self.assertIsNotNone(result.get("Extension.url"))
        action_info = result["Extension.url"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.source, ActionSource.SYSTEM_DEFAULT)
        self.assertEqual(
            action_info.fixed_value,
            "https://example.com/fhir/StructureDefinition/example-extension"
        )
        self.assertTrue(action_info.auto_generated)

    def test_fixed_string_detected_automatically(self):
        """Test that fixedString values are automatically detected."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        field = Mock()
        field.name = "Identifier.system"
        field.classification = "compatible"
        field.actions_allowed = [ActionType.USE, ActionType.FIXED]
        
        target_field = Mock()
        target_field.fixed_value = "http://example.com/identifier-system"
        target_field.fixed_value_type = "fixedString"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            "target-profile|1.0.0": target_field
        }
        
        mapping.fields = {
            "Identifier.system": field
        }
        
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        action_info = result["Identifier.system"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.fixed_value, "http://example.com/identifier-system")

    def test_fixed_code_detected_automatically(self):
        """Test that fixedCode values are automatically detected."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        field = Mock()
        field.name = "Coding.code"
        field.classification = "compatible"
        field.actions_allowed = [ActionType.USE, ActionType.FIXED]
        
        target_field = Mock()
        target_field.fixed_value = "test-code"
        target_field.fixed_value_type = "fixedCode"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            "target-profile|1.0.0": target_field
        }
        
        mapping.fields = {
            "Coding.code": field
        }
        
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        action_info = result["Coding.code"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.fixed_value, "test-code")

    def test_fixed_decimal_detected_automatically(self):
        """Test that fixedDecimal values are automatically detected."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        field = Mock()
        field.name = "Quantity.value"
        field.classification = "compatible"
        field.actions_allowed = [ActionType.USE, ActionType.FIXED]
        
        target_field = Mock()
        target_field.fixed_value = 1.0
        target_field.fixed_value_type = "fixedDecimal"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            "target-profile|1.0.0": target_field
        }
        
        mapping.fields = {
            "Quantity.value": field
        }
        
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        action_info = result["Quantity.value"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.fixed_value, 1.0)

    def test_manual_entry_overrides_detected_fixed_value(self):
        """Test that manual entries override automatically detected fixed values."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        field = Mock()
        field.name = "Extension.url"
        field.classification = "compatible"
        
        target_field = Mock()
        target_field.fixed_value = "https://auto-detected.com"
        target_field.fixed_value_type = "fixedUri"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            "target-profile|1.0.0": target_field
        }
        
        mapping.fields = {
            "Extension.url": field
        }
        
        # Manual entry with different fixed value
        manual_entries = {
            "Extension.url": {
                "action": "fixed",
                "fixed": "https://manual-override.com",
                "remark": "Manually set value"
            }
        }
        
        result = compute_mapping_actions(mapping, manual_entries=manual_entries)
        
        action_info = result["Extension.url"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.source, ActionSource.MANUAL)
        self.assertEqual(action_info.fixed_value, "https://manual-override.com")
        self.assertEqual(action_info.user_remark, "Manually set value")

    def test_no_fixed_value_when_target_field_missing(self):
        """Test that no FIXED action is set when target field doesn't exist."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        field = Mock()
        field.name = "Extension.url"
        field.classification = "incompatible"
        
        # No target profile field
        field.profiles = {
            "target-profile|1.0.0": None
        }
        
        mapping.fields = {
            "Extension.url": field
        }
        
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        action_info = result["Extension.url"]
        # Should not have FIXED action since target field is missing
        self.assertIsNone(action_info.action)

    def test_get_fixed_value_from_field_helper(self):
        """Test the _get_fixed_value_from_field helper function."""
        target_key = "target-profile|1.0.0"
        
        # Create field with fixed value
        field = Mock()
        field.name = "Extension.url"
        
        target_field = Mock()
        target_field.fixed_value = "https://example.com"
        target_field.pattern_coding_system = None
        
        field.profiles = {
            target_key: target_field
        }
        
        result = _get_fixed_value_from_field(field, target_key, {})
        self.assertEqual(result, "https://example.com")

    def test_get_fixed_value_returns_none_for_missing_field(self):
        """Test that helper returns None when target field is missing."""
        result = _get_fixed_value_from_field(None, "target-key", {})
        self.assertIsNone(result)

    def test_pattern_coding_system_takes_precedence_for_system_fields(self):
        """Test that patternCoding.system is used for .system fields."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        # Parent coding field with patternCoding
        parent_field = Mock()
        parent_field.name = "Coding"
        parent_target_field = Mock()
        parent_target_field.pattern_coding_system = "http://example.com/codesystem"
        parent_target_field.fixed_value = None
        parent_field.profiles = {
            "target-profile|1.0.0": parent_target_field
        }
        
        # .system child field
        system_field = Mock()
        system_field.name = "Coding.system"
        system_field.classification = "compatible"
        system_field.actions_allowed = [ActionType.USE, ActionType.FIXED]
        
        system_target_field = Mock()
        system_target_field.fixed_value = None  # No direct fixed value
        system_target_field.pattern_coding_system = None
        
        system_field.profiles = {
            "target-profile|1.0.0": system_target_field
        }
        
        mapping.fields = {
            "Coding": parent_field,
            "Coding.system": system_field
        }
        
        result = compute_mapping_actions(mapping, manual_entries=None)
        
        # .system field should get FIXED action from parent's patternCoding
        action_info = result["Coding.system"]
        self.assertEqual(action_info.action, ActionType.FIXED)
        self.assertEqual(action_info.fixed_value, "http://example.com/codesystem")


if __name__ == "__main__":
    unittest.main()
