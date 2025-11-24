"""Integration tests for recommendation conflict detection."""

import unittest
from unittest.mock import Mock

from structure_comparer.recommendation_engine import RecommendationEngine
from structure_comparer.model.mapping_action_models import ActionType


class TestRecommendationConflictDetection(unittest.TestCase):
    """Test that recommendations don't override existing actions."""

    def test_copy_to_recommendation_skipped_when_target_has_fixed_value(self):
        """Test NOT_USE recommendation when target has FIXED action.
        
        Scenario:
        - Source: Medication.extension:Impfstoff.url
        - Target: Medication.extension:isVaccine.url (has FIXED action from system)
        - Expected: NOT_USE recommendation instead of copy_to
        """
        # Setup mapping
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        # Parent field with copy_to action (manual entry)
        parent_source = Mock()
        parent_source.name = "Medication.extension:Impfstoff"
        parent_source.classification = "compatible"
        parent_source.actions_allowed = []
        
        parent_target = Mock()
        parent_source.profiles = {"target-profile|1.0.0": parent_target}
        
        # Child source field (where recommendation would appear)
        child_source = Mock()
        child_source.name = "Medication.extension:Impfstoff.url"
        child_source.classification = "compatible"
        child_source.actions_allowed = [ActionType.COPY_TO, ActionType.USE, ActionType.NOT_USE]
        
        child_source_target = Mock()
        child_source_target.fixed_value = None  # Source field has no fixed value
        child_source_target.pattern_coding_system = None
        child_source.profiles = {"target-profile|1.0.0": child_source_target}
        
        # Child target field (has FIXED value from system)
        child_target = Mock()
        child_target.name = "Medication.extension:isVaccine.url"
        child_target.classification = "compatible"
        child_target.actions_allowed = []
        
        child_target_profile = Mock()
        child_target_profile.fixed_value = (
            "https://gematik.de/fhir/epa-medication/"
            "StructureDefinition/medication-id-vaccine-extension"
        )
        child_target_profile.pattern_coding_system = None
        
        child_target.profiles = {"target-profile|1.0.0": child_target_profile}
        
        # Add parent target field (must exist for inheritance to work)
        parent_target_field = Mock()
        parent_target_field.name = "Medication.extension:isVaccine"
        parent_target_field.classification = "compatible"
        parent_target_field.actions_allowed = []
        parent_target_profile = Mock()
        parent_target_profile.fixed_value = None
        parent_target_profile.pattern_coding_system = None
        parent_target_field.profiles = {"target-profile|1.0.0": parent_target_profile}
        
        mapping.fields = {
            "Medication.extension:Impfstoff": parent_source,
            "Medication.extension:isVaccine": parent_target_field,
            "Medication.extension:Impfstoff.url": child_source,
            "Medication.extension:isVaccine.url": child_target,
        }
        
        # Manual entry for parent: copy_to
        manual_entries = {
            "Medication.extension:Impfstoff": {
                "action": "copy_to",
                "other": "Medication.extension:isVaccine",
                "remark": "Map vaccine extension",
            }
        }
        
        # Compute recommendations
        engine = RecommendationEngine(mapping, manual_entries)
        recommendations = engine.compute_all_recommendations()
        
        # Verify: NOT_USE recommendation instead of copy_to
        child_recs = recommendations.get("Medication.extension:Impfstoff.url", [])
        
        # Should have NOT_USE recommendation
        not_use_recs = [r for r in child_recs if r.action == ActionType.NOT_USE]
        self.assertEqual(
            len(not_use_recs), 1,
            "Should create NOT_USE recommendation when target has FIXED value"
        )
        
        # Should NOT have copy_to recommendation
        copy_to_recs = [r for r in child_recs if r.action == ActionType.COPY_TO]
        self.assertEqual(
            len(copy_to_recs), 0,
            "Should NOT create copy_to recommendation when target has FIXED value"
        )
        
        # Verify the remark mentions the fixed value
        not_use_rec = not_use_recs[0]
        self.assertIsNotNone(not_use_rec.system_remarks)
        has_fixed_value_mention = any(
            "fixed value" in remark.lower() and "isVaccine.url" in remark
            for remark in not_use_rec.system_remarks
        )
        self.assertTrue(
            has_fixed_value_mention,
            f"Should mention fixed value in remark. Got: {not_use_rec.system_remarks}"
        )

    def test_copy_to_recommendation_created_when_target_has_no_action(self):
        """Test that copy_to recommendation IS created when target has no action."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        # Parent with copy_to
        parent_source = Mock()
        parent_source.name = "Extension.valueString"
        parent_source.classification = "compatible"
        parent_source.actions_allowed = []
        parent_source.profiles = {"target-profile|1.0.0": Mock()}
        
        # Child source
        child_source = Mock()
        child_source.name = "Extension.valueString.id"
        child_source.classification = "compatible"
        child_source.actions_allowed = [ActionType.COPY_TO]
        child_source.profiles = {"target-profile|1.0.0": Mock()}
        
        # Child target (NO action)
        child_target = Mock()
        child_target.name = "Extension.valueBoolean.id"
        child_target.classification = "compatible"
        child_target.actions_allowed = []
        
        child_target_profile = Mock()
        child_target_profile.fixed_value = None
        child_target_profile.pattern_coding_system = None
        
        child_target.profiles = {"target-profile|1.0.0": child_target_profile}
        
        mapping.fields = {
            "Extension.valueString": parent_source,
            "Extension.valueString.id": child_source,
            "Extension.valueBoolean.id": child_target,
        }
        
        manual_entries = {
            "Extension.valueString": {
                "action": "copy_to",
                "other": "Extension.valueBoolean",
            }
        }
        
        engine = RecommendationEngine(mapping, manual_entries)
        recommendations = engine.compute_all_recommendations()
        
        # Should have recommendation since target has no action
        child_recs = recommendations.get("Extension.valueString.id", [])
        self.assertGreater(
            len(child_recs), 0,
            "Should create copy_to recommendation when target has no action"
        )
        self.assertEqual(child_recs[0].action, ActionType.COPY_TO)
        self.assertEqual(child_recs[0].other_value, "Extension.valueBoolean.id")

    def test_copy_to_recommendation_skipped_when_target_has_manual_action(self):
        """Test that copy_to recommendation is not created when target has manual action."""
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        parent_source = Mock()
        parent_source.name = "Medication.code"
        parent_source.classification = "compatible"
        parent_source.actions_allowed = []
        parent_source.profiles = {"target-profile|1.0.0": Mock()}
        
        child_source = Mock()
        child_source.name = "Medication.code.coding"
        child_source.classification = "compatible"
        child_source.actions_allowed = [ActionType.COPY_TO]
        child_source.profiles = {"target-profile|1.0.0": Mock()}
        
        child_target = Mock()
        child_target.name = "Medication.ingredient.itemCodeableConcept"
        child_target.classification = "compatible"
        child_target.actions_allowed = []
        
        child_target_profile = Mock()
        child_target_profile.fixed_value = None
        child_target_profile.pattern_coding_system = None
        
        child_target.profiles = {"target-profile|1.0.0": child_target_profile}
        
        mapping.fields = {
            "Medication.code": parent_source,
            "Medication.code.coding": child_source,
            "Medication.ingredient.itemCodeableConcept": child_target,
        }
        
        manual_entries = {
            "Medication.code": {
                "action": "copy_to",
                "other": "Medication.ingredient",
            },
            # Target child has manual USE action
            "Medication.ingredient.itemCodeableConcept": {
                "action": "use",
                "remark": "Manually configured",
            }
        }
        
        engine = RecommendationEngine(mapping, manual_entries)
        recommendations = engine.compute_all_recommendations()
        
        # Should NOT have recommendation since target has manual action
        child_recs = recommendations.get("Medication.code.coding", [])
        self.assertEqual(
            len(child_recs), 0,
            "Should not create copy_to recommendation when target has manual action"
        )

    def test_copy_from_recommendation_not_affected_by_target(self):
        """Test that copy_from recommendations are not affected by target field status.
        
        copy_from pulls data FROM another field, so the target field's action
        should not prevent the recommendation (only affects the source field itself).
        """
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        parent_source = Mock()
        parent_source.name = "Medication.extension:A"
        parent_source.classification = "compatible"
        parent_source.actions_allowed = []
        parent_source.profiles = {"target-profile|1.0.0": Mock()}
        
        child_source = Mock()
        child_source.name = "Medication.extension:A.url"
        child_source.classification = "compatible"
        child_source.actions_allowed = [ActionType.COPY_FROM]
        child_source.profiles = {"target-profile|1.0.0": Mock()}
        
        # Other field (copy source) has FIXED value
        other_field = Mock()
        other_field.name = "Medication.extension:B.url"
        other_field.classification = "compatible"
        other_field.actions_allowed = []
        
        other_profile = Mock()
        other_profile.fixed_value = "https://example.com/fixed"
        other_profile.pattern_coding_system = None
        
        other_field.profiles = {"target-profile|1.0.0": other_profile}
        
        mapping.fields = {
            "Medication.extension:A": parent_source,
            "Medication.extension:A.url": child_source,
            "Medication.extension:B.url": other_field,
        }
        
        manual_entries = {
            "Medication.extension:A": {
                "action": "copy_from",
                "other": "Medication.extension:B",
            }
        }
        
        engine = RecommendationEngine(mapping, manual_entries)
        recommendations = engine.compute_all_recommendations()
        
        # copy_from should still create recommendation
        # (it's pulling FROM B.url, not pushing TO B.url)
        child_recs = recommendations.get("Medication.extension:A.url", [])
        self.assertGreater(
            len(child_recs), 0,
            "copy_from recommendations should be created regardless of source field status"
        )
        self.assertEqual(child_recs[0].action, ActionType.COPY_FROM)

    def test_copy_to_recommendation_includes_fixed_value_remark(self):
        """Test that NOT_USE recommendation is created when target has FIXED value.
        
        This test validates that when a parent has copy_to and the child target
        has a FIXED value, a NOT_USE recommendation is created for the source field.
        """
        mapping = Mock()
        target = Mock()
        target.key = "target-profile|1.0.0"
        mapping.target = target
        
        # Parent with copy_to (manual)
        parent_source = Mock()
        parent_source.name = "Medication.extension:Impfstoff"
        parent_source.classification = "compatible"
        parent_source.actions_allowed = []
        parent_source.profiles = {"target-profile|1.0.0": Mock()}
        
        # Parent target
        parent_target = Mock()
        parent_target.name = "Medication.extension:isVaccine"
        parent_target.classification = "compatible"
        parent_target.actions_allowed = []
        
        parent_target_profile = Mock()
        parent_target_profile.fixed_value = None
        parent_target_profile.pattern_coding_system = None
        parent_target.profiles = {"target-profile|1.0.0": parent_target_profile}
        
        # Child source (no fixed value)
        child_source = Mock()
        child_source.name = "Medication.extension:Impfstoff.url"
        child_source.classification = "compatible"
        child_source.actions_allowed = [ActionType.COPY_TO, ActionType.USE, ActionType.NOT_USE]
        
        child_source_profile = Mock()
        child_source_profile.fixed_value = None
        child_source_profile.pattern_coding_system = None
        child_source.profiles = {"target-profile|1.0.0": child_source_profile}
        
        # Child target (HAS fixed value -> will get FIXED action)
        child_target = Mock()
        child_target.name = "Medication.extension:isVaccine.url"
        child_target.classification = "compatible"
        child_target.actions_allowed = []
        
        child_target_profile = Mock()
        child_target_profile.fixed_value = (
            "https://gematik.de/fhir/epa-medication/"
            "StructureDefinition/medication-id-vaccine-extension"
        )
        child_target_profile.pattern_coding_system = None
        child_target.profiles = {"target-profile|1.0.0": child_target_profile}
        
        mapping.fields = {
            "Medication.extension:Impfstoff": parent_source,
            "Medication.extension:isVaccine": parent_target,
            "Medication.extension:Impfstoff.url": child_source,
            "Medication.extension:isVaccine.url": child_target,
        }
        
        # Manual entry: Parent has copy_to, and target parent has USE (to avoid conflict on parent level)
        manual_entries = {
            "Medication.extension:Impfstoff": {
                "action": "copy_to",
                "other": "Medication.extension:isVaccine",
            },
            "Medication.extension:isVaccine": {
                "action": "use",  # Manual USE to prevent FIXED inheritance to parent
            }
        }
        
        engine = RecommendationEngine(mapping, manual_entries)
        recommendations = engine.compute_all_recommendations()
        
        # The child source should have NOT_USE recommendation (not copy_to)
        child_recs = recommendations.get("Medication.extension:Impfstoff.url", [])
        
        not_use_recs = [r for r in child_recs if r.action == ActionType.NOT_USE]
        self.assertEqual(
            len(not_use_recs), 1,
            "Should create NOT_USE recommendation when target has fixed value"
        )
        
        # Verify remark mentions fixed value
        rec = not_use_recs[0]
        has_fixed_mention = any(
            "fixed value" in remark.lower()
            for remark in (rec.system_remarks or [])
        )
        self.assertTrue(has_fixed_mention, f"Should mention fixed value. Got: {rec.system_remarks}")


if __name__ == "__main__":
    unittest.main()
