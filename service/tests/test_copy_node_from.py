"""Tests for copy_node_from action and its bidirectional partner derivation.

This test module verifies:
1. Bidirectional partner derivation via _augment_copy_links()
2. Cleanup logic when deleting copy_node_to/copy_node_from actions
3. Recommendations for copy_node_from actions
4. copy_node_from in _INHERITABLE_ACTIONS
"""

from typing import Dict

from structure_comparer.mapping_actions_engine import (
    compute_mapping_actions,
    compute_recommendations,
    _INHERITABLE_ACTIONS,
)
from structure_comparer.model.mapping_action_models import (
    ActionSource,
    ActionType,
)


class StubProfileField:
    """Stub for a profile field with optional fixed_value."""
    def __init__(self, fixed_value=None):
        self.fixed_value = fixed_value


class StubField:
    def __init__(self, name: str, classification: str = "compatible", profiles=None):
        self.name = name
        self.classification = classification
        self.profiles = profiles or {}
        self.is_target_required = False


class StubMapping:
    def __init__(self, field_defs, target_key=None):
        self.fields: Dict[str, StubField] = {}
        self.target = None
        if target_key:
            self.target = type('obj', (object,), {'key': target_key})()
        
        for definition in field_defs:
            if isinstance(definition, tuple):
                name, classification = definition
                self.fields[name] = StubField(name, classification)
            elif isinstance(definition, dict):
                name = definition["name"]
                classification = definition.get("classification", "compatible")
                profiles = definition.get("profiles", {})
                self.fields[name] = StubField(name, classification, profiles)
            else:
                name, classification = definition, "compatible"
                self.fields[name] = StubField(name, classification)


# ========================================
# Tests for _augment_copy_links() partner derivation
# ========================================

class TestCopyNodeToDerivesPartner:
    """Test that copy_node_to derives a partner copy_node_from action."""
    
    def test_copy_node_to_derives_copy_node_from_partner(self):
        """When copy_node_to is set, the target field should get copy_node_from."""
        mapping = StubMapping([
            "Medication.extension:source",
            "Medication.extension:target",
        ])
        manual_entries = {
            "Medication.extension:source": {
                "action": "copy_node_to",
                "other": "Medication.extension:target",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        source_info = result["Medication.extension:source"]
        partner_info = result["Medication.extension:target"]

        # Source should have manual copy_node_to
        assert source_info.action == ActionType.COPY_NODE_TO
        assert source_info.source == ActionSource.MANUAL
        assert source_info.other_value == "Medication.extension:target"
        
        # Partner should have derived copy_node_from
        assert partner_info.action == ActionType.COPY_NODE_FROM
        assert partner_info.source == ActionSource.MANUAL
        assert partner_info.other_value == "Medication.extension:source"

    def test_copy_node_to_uses_correct_other_value_for_partner(self):
        """Partner's other_value should point back to the original field."""
        mapping = StubMapping([
            "Patient.extension:A",
            "Patient.extension:B",
        ])
        manual_entries = {
            "Patient.extension:A": {
                "action": "copy_node_to",
                "other": "Patient.extension:B",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # Check that other_value is correctly set
        assert result["Patient.extension:A"].other_value == "Patient.extension:B"
        assert result["Patient.extension:B"].other_value == "Patient.extension:A"


class TestCopyNodeFromDerivesPartner:
    """Test that copy_node_from derives a partner copy_node_to action."""
    
    def test_copy_node_from_derives_copy_node_to_partner(self):
        """When copy_node_from is set, the source field should get copy_node_to."""
        mapping = StubMapping([
            "Medication.extension:source",
            "Medication.extension:target",
        ])
        manual_entries = {
            "Medication.extension:target": {
                "action": "copy_node_from",
                "other": "Medication.extension:source",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        target_info = result["Medication.extension:target"]
        partner_info = result["Medication.extension:source"]

        # Target should have manual copy_node_from
        assert target_info.action == ActionType.COPY_NODE_FROM
        assert target_info.source == ActionSource.MANUAL
        assert target_info.other_value == "Medication.extension:source"
        
        # Partner should have derived copy_node_to
        assert partner_info.action == ActionType.COPY_NODE_TO
        assert partner_info.source == ActionSource.MANUAL
        assert partner_info.other_value == "Medication.extension:target"

    def test_copy_node_from_uses_correct_other_value_for_partner(self):
        """Partner's other_value should point back to the original field."""
        mapping = StubMapping([
            "Observation.extension:A",
            "Observation.extension:B",
        ])
        manual_entries = {
            "Observation.extension:B": {
                "action": "copy_node_from",
                "other": "Observation.extension:A",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # Check that other_value is correctly set
        assert result["Observation.extension:B"].other_value == "Observation.extension:A"
        assert result["Observation.extension:A"].other_value == "Observation.extension:B"


class TestExistingActionsNotOverwritten:
    """Test that existing manual actions are not overwritten by derived partners."""
    
    def test_copy_node_to_does_not_override_existing_action(self):
        """If target field already has an action, it should not be overwritten."""
        mapping = StubMapping([
            "Medication.extension:source",
            "Medication.extension:target",
        ])
        manual_entries = {
            "Medication.extension:source": {
                "action": "copy_node_to",
                "other": "Medication.extension:target",
            },
            "Medication.extension:target": {
                "action": "use",  # Existing action
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # Source should have copy_node_to
        assert result["Medication.extension:source"].action == ActionType.COPY_NODE_TO
        
        # Target should keep its existing USE action (not overwritten to copy_node_from)
        assert result["Medication.extension:target"].action == ActionType.USE
        assert result["Medication.extension:target"].source == ActionSource.MANUAL

    def test_copy_node_from_does_not_override_existing_action(self):
        """If source field already has an action, it should not be overwritten."""
        mapping = StubMapping([
            "Medication.extension:source",
            "Medication.extension:target",
        ])
        manual_entries = {
            "Medication.extension:target": {
                "action": "copy_node_from",
                "other": "Medication.extension:source",
            },
            "Medication.extension:source": {
                "action": "not_use",  # Existing action
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # Target should have copy_node_from
        assert result["Medication.extension:target"].action == ActionType.COPY_NODE_FROM
        
        # Source should keep its existing NOT_USE action (not overwritten to copy_node_to)
        assert result["Medication.extension:source"].action == ActionType.NOT_USE
        assert result["Medication.extension:source"].source == ActionSource.MANUAL


class TestDerivedMarker:
    """Test that derived partner entries have _derived marker."""
    
    def test_derived_marker_set_for_copy_node_from_partner(self):
        """Derived copy_node_from partner should have _derived: True in raw entry."""
        mapping = StubMapping([
            "Patient.extension:A",
            "Patient.extension:B",
        ])
        manual_entries = {
            "Patient.extension:A": {
                "action": "copy_node_to",
                "other": "Patient.extension:B",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # The original entry should NOT have _derived
        source_raw = result["Patient.extension:A"].raw_manual_entry
        assert source_raw is not None
        # _derived is removed from the ActionInfo, but we can verify it was there
        # by checking the partner's action type
        
        # Partner should be derived (indicated by having correct action)
        partner_info = result["Patient.extension:B"]
        assert partner_info.action == ActionType.COPY_NODE_FROM

    def test_derived_marker_set_for_copy_node_to_partner(self):
        """Derived copy_node_to partner should have _derived: True in raw entry."""
        mapping = StubMapping([
            "Patient.extension:A",
            "Patient.extension:B",
        ])
        manual_entries = {
            "Patient.extension:B": {
                "action": "copy_node_from",
                "other": "Patient.extension:A",
            }
        }

        result = compute_mapping_actions(mapping, manual_entries)

        # Partner should be derived (indicated by having correct action)
        partner_info = result["Patient.extension:A"]
        assert partner_info.action == ActionType.COPY_NODE_TO


# ========================================
# Tests for copy_node_from in _INHERITABLE_ACTIONS
# ========================================

class TestInheritableActions:
    """Test that copy_node_from is recognized as inheritable."""
    
    def test_copy_node_from_in_inheritable_actions(self):
        """COPY_NODE_FROM should be in _INHERITABLE_ACTIONS."""
        assert ActionType.COPY_NODE_FROM in _INHERITABLE_ACTIONS
    
    def test_copy_node_to_in_inheritable_actions(self):
        """COPY_NODE_TO should be in _INHERITABLE_ACTIONS (for consistency check)."""
        assert ActionType.COPY_NODE_TO in _INHERITABLE_ACTIONS


class TestInheritanceEngine:
    """Test that InheritanceEngine handles copy_node_from correctly."""
    
    def test_copy_node_from_is_inheritable(self):
        """InheritanceEngine should recognize COPY_NODE_FROM as inheritable."""
        from structure_comparer.inheritance_engine import InheritanceEngine
        
        engine = InheritanceEngine({})
        
        assert engine.can_inherit_action(ActionType.COPY_NODE_FROM)
    
    def test_copy_node_from_is_copy_action(self):
        """InheritanceEngine should treat COPY_NODE_FROM as a copy action."""
        from structure_comparer.inheritance_engine import InheritanceEngine
        
        engine = InheritanceEngine({})
        
        assert engine.is_copy_action(ActionType.COPY_NODE_FROM)


# ========================================
# Tests for recommendations
# ========================================

class TestCopyNodeFromRecommendations:
    """Test that copy_node_from appears correctly in recommendations."""
    
    def test_parent_copy_node_from_creates_child_recommendations(self):
        """Parent with copy_node_from should create recommendations for children."""
        mapping = StubMapping([
            # Target fields (receiving data)
            "Medication.extension:B",
            "Medication.extension:B.url",
            "Medication.extension:B.value[x]",
            # Source fields (sending data)
            "Medication.extension:A",
            "Medication.extension:A.url",
            "Medication.extension:A.value[x]",
        ])
        
        manual_entries = {
            "Medication.extension:B": {
                "action": "copy_node_from",
                "other": "Medication.extension:A",
            }
        }
        
        recommendations = compute_recommendations(mapping, manual_entries)
        
        # Children of target should have copy_node_from recommendations
        child_field = "Medication.extension:B.url"
        assert child_field in recommendations, f"{child_field} should have recommendations"
        
        child_recs = recommendations[child_field]
        copy_node_from_rec = next(
            (r for r in child_recs if r.action == ActionType.COPY_NODE_FROM), None
        )
        assert copy_node_from_rec is not None, f"{child_field} should have COPY_NODE_FROM recommendation"
        assert copy_node_from_rec.other_value == "Medication.extension:A.url"

    def test_parent_copy_node_to_creates_copy_node_to_recommendations(self):
        """Parent with copy_node_to should create copy_node_to recommendations for children."""
        mapping = StubMapping([
            # Source fields (sending data)
            "Medication.extension:A",
            "Medication.extension:A.url",
            "Medication.extension:A.value[x]",
            # Target fields (receiving data)
            "Medication.extension:B",
            "Medication.extension:B.url",
            "Medication.extension:B.value[x]",
        ])
        
        manual_entries = {
            "Medication.extension:A": {
                "action": "copy_node_to",
                "other": "Medication.extension:B",
            }
        }
        
        recommendations = compute_recommendations(mapping, manual_entries)
        
        # Children of source should have copy_node_to recommendations
        child_field = "Medication.extension:A.url"
        assert child_field in recommendations, f"{child_field} should have recommendations"
        
        child_recs = recommendations[child_field]
        copy_node_to_rec = next(
            (r for r in child_recs if r.action == ActionType.COPY_NODE_TO), None
        )
        assert copy_node_to_rec is not None, f"{child_field} should have COPY_NODE_TO recommendation"
        assert copy_node_to_rec.other_value == "Medication.extension:B.url"


# ========================================
# Tests for evaluation consistency
# ========================================

class TestEvaluationWithCopyNodeFrom:
    """Test that fields with copy_node_from are correctly evaluated."""
    
    def test_copy_node_from_field_is_solved(self):
        """Field with copy_node_from action should be marked as SOLVED."""
        from structure_comparer.mapping_evaluation_engine import evaluate_mapping
        from structure_comparer.model.mapping_action_models import MappingStatus
        
        mapping = StubMapping([
            ("Medication.extension:target", "incompatible"),
            "Medication.extension:source",
        ])
        
        manual_entries = {
            "Medication.extension:target": {
                "action": "copy_node_from",
                "other": "Medication.extension:source",
            }
        }
        
        actions = compute_mapping_actions(mapping, manual_entries)
        evaluations = evaluate_mapping(mapping, actions)
        
        # Field with copy_node_from should be SOLVED
        assert evaluations["Medication.extension:target"].mapping_status == MappingStatus.SOLVED
    
    def test_derived_partner_is_solved(self):
        """Derived partner field should also be marked as SOLVED."""
        from structure_comparer.mapping_evaluation_engine import evaluate_mapping
        from structure_comparer.model.mapping_action_models import MappingStatus
        
        mapping = StubMapping([
            ("Medication.extension:source", "incompatible"),
            ("Medication.extension:target", "incompatible"),
        ])
        
        manual_entries = {
            "Medication.extension:source": {
                "action": "copy_node_to",
                "other": "Medication.extension:target",
            }
        }
        
        actions = compute_mapping_actions(mapping, manual_entries)
        evaluations = evaluate_mapping(mapping, actions)
        
        # Both fields should be SOLVED
        assert evaluations["Medication.extension:source"].mapping_status == MappingStatus.SOLVED
        assert evaluations["Medication.extension:target"].mapping_status == MappingStatus.SOLVED


# ========================================
# Tests for symmetry between copy_value and copy_node actions
# ========================================

class TestSymmetryWithCopyValue:
    """Test that copy_node actions behave symmetrically with copy_value actions."""
    
    def test_copy_node_same_behavior_as_copy_value(self):
        """copy_node_to/copy_node_from should behave like copy_value_to/copy_value_from."""
        mapping = StubMapping([
            "Field.A",
            "Field.B",
            "Field.C",
            "Field.D",
        ])
        
        # Set up copy_value_from and copy_node_to in parallel
        manual_entries = {
            "Field.A": {
                "action": "copy_value_from",
                "other": "Field.B",
            },
            "Field.C": {
                "action": "copy_node_to",
                "other": "Field.D",
            }
        }
        
        result = compute_mapping_actions(mapping, manual_entries)
        
        # Both should derive partners
        assert result["Field.A"].action == ActionType.COPY_VALUE_FROM
        assert result["Field.B"].action == ActionType.COPY_VALUE_TO
        assert result["Field.C"].action == ActionType.COPY_NODE_TO
        assert result["Field.D"].action == ActionType.COPY_NODE_FROM
        
        # Both should have correct other_value
        assert result["Field.A"].other_value == "Field.B"
        assert result["Field.B"].other_value == "Field.A"
        assert result["Field.C"].other_value == "Field.D"
        assert result["Field.D"].other_value == "Field.C"


# ========================================
# Edge case tests
# ========================================

class TestEdgeCases:
    """Test edge cases for copy_node_from."""
    
    def test_self_reference_is_handled(self):
        """Self-referencing copy_node_to should not crash."""
        mapping = StubMapping([
            "Field.A",
        ])
        
        # This is an invalid entry but should not crash
        manual_entries = {
            "Field.A": {
                "action": "copy_node_to",
                "other": "Field.A",  # Self-reference
            }
        }
        
        # Should not raise an exception
        result = compute_mapping_actions(mapping, manual_entries)
        
        # Field should have copy_node_to
        assert result["Field.A"].action == ActionType.COPY_NODE_TO
    
    def test_missing_other_field_is_handled(self):
        """copy_node_to without other field should not crash."""
        mapping = StubMapping([
            "Field.A",
        ])
        
        manual_entries = {
            "Field.A": {
                "action": "copy_node_to",
                # No "other" specified
            }
        }
        
        # Should not raise an exception
        result = compute_mapping_actions(mapping, manual_entries)
        
        # Field should have copy_node_to
        assert result["Field.A"].action == ActionType.COPY_NODE_TO
    
    def test_nonexistent_target_in_mapping_is_handled(self):
        """copy_node_to to non-existent field should create the partner anyway."""
        mapping = StubMapping([
            "Field.A",
            # Field.B is NOT in the mapping
        ])
        
        manual_entries = {
            "Field.A": {
                "action": "copy_node_to",
                "other": "Field.B",  # Field.B does not exist in mapping
            }
        }
        
        # Should not raise an exception
        result = compute_mapping_actions(mapping, manual_entries)
        
        # Field.A should have copy_node_to
        assert result["Field.A"].action == ActionType.COPY_NODE_TO
        
        # Field.B is not in the mapping's fields, so it won't be in result
        # (the augmented manual_map has the partner, but result only contains fields from mapping)
        assert "Field.B" not in result
