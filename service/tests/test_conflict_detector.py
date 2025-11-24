"""Unit tests for conflict_detector module."""

import unittest

from structure_comparer.conflict_detector import ConflictDetector
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
)


class TestConflictDetector(unittest.TestCase):
    """Test cases for ConflictDetector class."""

    def test_has_active_action_with_fixed_action(self):
        """Test that a field with FIXED action is detected as having an active action."""
        action_map = {
            "Extension.url": ActionInfo(
                action=ActionType.FIXED,
                source=ActionSource.SYSTEM_DEFAULT,
                auto_generated=True,
                fixed_value="https://example.com",
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertTrue(detector.has_active_action("Extension.url"))

    def test_has_active_action_with_manual_action(self):
        """Test that a field with manual action is detected as having an active action."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.USE,
                source=ActionSource.MANUAL,
                auto_generated=False,
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertTrue(detector.has_active_action("Medication.code"))

    def test_has_active_action_with_none_action(self):
        """Test that a field with None action is not detected as having an active action."""
        action_map = {
            "Medication.code": ActionInfo(
                action=None,  # No action selected yet
                source=ActionSource.SYSTEM_DEFAULT,
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertFalse(detector.has_active_action("Medication.code"))

    def test_has_active_action_field_not_in_map(self):
        """Test that a field not in the action map is not detected as having an active action."""
        action_map = {}
        
        detector = ConflictDetector(action_map)
        self.assertFalse(detector.has_active_action("Medication.code"))

    def test_would_override_action_with_same_action(self):
        """Test that same action type does not constitute an override."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.USE,
                source=ActionSource.MANUAL,
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertFalse(
            detector.would_override_action("Medication.code", ActionType.USE)
        )

    def test_would_override_action_with_different_action(self):
        """Test that different action type constitutes an override."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.USE,
                source=ActionSource.MANUAL,
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertTrue(
            detector.would_override_action("Medication.code", ActionType.NOT_USE)
        )

    def test_would_override_action_with_no_existing_action(self):
        """Test that recommending an action for a field with no action is not an override."""
        action_map = {
            "Medication.code": ActionInfo(
                action=None,
                source=ActionSource.SYSTEM_DEFAULT,
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertFalse(
            detector.would_override_action("Medication.code", ActionType.USE)
        )

    def test_would_override_copy_action_same_target(self):
        """Test that same copy action with same target is not an override."""
        action_map = {
            "Extension.url": ActionInfo(
                action=ActionType.COPY_TO,
                source=ActionSource.MANUAL,
                other_value="OtherExtension.url",
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertFalse(
            detector.would_override_action(
                "Extension.url", ActionType.COPY_TO, "OtherExtension.url"
            )
        )

    def test_would_override_copy_action_different_target(self):
        """Test that same copy action with different target is an override."""
        action_map = {
            "Extension.url": ActionInfo(
                action=ActionType.COPY_TO,
                source=ActionSource.MANUAL,
                other_value="OtherExtension.url",
            )
        }
        
        detector = ConflictDetector(action_map)
        self.assertTrue(
            detector.would_override_action(
                "Extension.url", ActionType.COPY_TO, "DifferentExtension.url"
            )
        )

    def test_get_target_field_conflict_with_fixed_value(self):
        """Test detecting conflict when target field has a FIXED action."""
        action_map = {
            "Medication.extension:isVaccine.url": ActionInfo(
                action=ActionType.FIXED,
                source=ActionSource.SYSTEM_DEFAULT,
                auto_generated=True,
                fixed_value=(
                    "https://gematik.de/fhir/epa-medication/"
                    "StructureDefinition/medication-id-vaccine-extension"
                ),
            )
        }
        
        detector = ConflictDetector(action_map)
        conflict = detector.get_target_field_conflict(
            "Medication.extension:Impfstoff.url",
            "Medication.extension:isVaccine.url",
            ActionType.COPY_TO,
        )
        
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.action, ActionType.FIXED)
        self.assertTrue(conflict.auto_generated)

    def test_get_target_field_conflict_with_manual_action(self):
        """Test detecting conflict when target field has a manual action."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.USE,
                source=ActionSource.MANUAL,
                auto_generated=False,
            )
        }
        
        detector = ConflictDetector(action_map)
        conflict = detector.get_target_field_conflict(
            "Medication.code.coding",
            "Medication.code",
            ActionType.COPY_TO,
        )
        
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.action, ActionType.USE)
        self.assertFalse(conflict.auto_generated)

    def test_get_target_field_conflict_no_conflict(self):
        """Test that no conflict is detected when target field has no action."""
        action_map = {
            "Medication.extension:isVaccine.url": ActionInfo(
                action=None,
                source=ActionSource.SYSTEM_DEFAULT,
            )
        }
        
        detector = ConflictDetector(action_map)
        conflict = detector.get_target_field_conflict(
            "Medication.extension:Impfstoff.url",
            "Medication.extension:isVaccine.url",
            ActionType.COPY_TO,
        )
        
        self.assertIsNone(conflict)

    def test_get_target_field_conflict_only_for_copy_to(self):
        """Test that conflict detection only applies to COPY_TO actions."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.FIXED,
                source=ActionSource.SYSTEM_DEFAULT,
                fixed_value="test",
            )
        }
        
        detector = ConflictDetector(action_map)
        
        # Should return None for non-COPY_TO actions
        conflict = detector.get_target_field_conflict(
            "Medication.code",
            "Medication.code.coding",
            ActionType.USE,
        )
        
        self.assertIsNone(conflict)

    def test_get_conflict_message_system_generated(self):
        """Test conflict message generation for system-generated actions."""
        action_map = {}
        detector = ConflictDetector(action_map)
        
        conflicting_action = ActionInfo(
            action=ActionType.FIXED,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            fixed_value="https://example.com",
        )
        
        message = detector.get_conflict_message(
            "Extension.url", ActionType.COPY_TO, conflicting_action
        )
        
        self.assertIn("system-generated", message)
        self.assertIn("FIXED", message)
        self.assertIn("Extension.url", message)

    def test_get_conflict_message_manual(self):
        """Test conflict message generation for manual actions."""
        action_map = {}
        detector = ConflictDetector(action_map)
        
        conflicting_action = ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
            auto_generated=False,
        )
        
        message = detector.get_conflict_message(
            "Medication.code", ActionType.USE_RECURSIVE, conflicting_action
        )
        
        self.assertIn("manually configured", message)
        self.assertIn("USE", message)
        self.assertIn("Medication.code", message)

    def test_target_field_not_in_map(self):
        """Test that missing target field does not cause errors."""
        action_map = {}
        
        detector = ConflictDetector(action_map)
        conflict = detector.get_target_field_conflict(
            "Medication.extension:A.url",
            "Medication.extension:B.url",
            ActionType.COPY_TO,
        )
        
        self.assertIsNone(conflict)

    def test_get_target_fixed_value_info_with_fixed_action(self):
        """Test that fixed value info is returned for target with FIXED action."""
        action_map = {
            "Medication.extension:isVaccine.url": ActionInfo(
                action=ActionType.FIXED,
                source=ActionSource.SYSTEM_DEFAULT,
                auto_generated=True,
                fixed_value="https://gematik.de/fhir/vaccine-extension",
            )
        }
        
        detector = ConflictDetector(action_map)
        fixed_value = detector.get_target_fixed_value_info("Medication.extension:isVaccine.url")
        
        self.assertEqual(fixed_value, "https://gematik.de/fhir/vaccine-extension")

    def test_get_target_fixed_value_info_without_fixed_action(self):
        """Test that None is returned when target has no FIXED action."""
        action_map = {
            "Medication.code": ActionInfo(
                action=ActionType.USE,
                source=ActionSource.MANUAL,
                auto_generated=False,
            )
        }
        
        detector = ConflictDetector(action_map)
        fixed_value = detector.get_target_fixed_value_info("Medication.code")
        
        self.assertIsNone(fixed_value)

    def test_get_target_fixed_value_info_field_not_in_map(self):
        """Test that None is returned when target field is not in action map."""
        action_map = {}
        
        detector = ConflictDetector(action_map)
        fixed_value = detector.get_target_fixed_value_info("Medication.unknown")
        
        self.assertIsNone(fixed_value)

    def test_get_target_fixed_value_info_fixed_without_other_value(self):
        """Test that None is returned when FIXED action has no fixed_value."""
        action_map = {
            "Extension.url": ActionInfo(
                action=ActionType.FIXED,
                source=ActionSource.SYSTEM_DEFAULT,
                auto_generated=True,
                fixed_value=None,  # No value provided
            )
        }
        
        detector = ConflictDetector(action_map)
        fixed_value = detector.get_target_fixed_value_info("Extension.url")
        
        self.assertIsNone(fixed_value)


if __name__ == "__main__":
    unittest.main()
