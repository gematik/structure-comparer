"""
Unit tests for child action propagation module

Tests the automatic propagation of parent mapping actions (NOT_USE, EMPTY) to child fields
with proper auto_generated flag management.
"""

import unittest
from unittest.mock import Mock
from structure_comparer.child_action_propagation import propagate_parent_actions_to_children


class TestChildActionPropagation(unittest.TestCase):
    
    def setUp(self):
        """Set up common test data"""
        self.mapping_id = "test-mapping-123"
        
        # Mock project with field structure
        self.mock_project = Mock()
        self.mock_mapping = Mock()
        
        # Define field hierarchy for Practitioner.meta.tag
        self.field_hierarchy = {
            "Practitioner.meta.tag": [
                "Practitioner.meta.tag:Origin",
                "Practitioner.meta.tag:profile:forProfile"
            ],
            "Practitioner.meta.tag:Origin": [],
            "Practitioner.meta.tag:profile:forProfile": []
        }
        
        # Mock mapping fields - create a dynamic fields dictionary
        self.mock_fields = {}
        for field_name in self.field_hierarchy.keys():
            mock_field = Mock()
            mock_field.name = field_name
            self.mock_fields[field_name] = mock_field
        
        self.mock_mapping.fields = self.mock_fields
        self.mock_project.get_mapping.return_value = self.mock_mapping
    
    def _create_manual_entries_data(self, fields_data):
        """Helper to create manual entries data structure"""
        return {
            "entries": [
                {
                    "id": self.mapping_id,
                    "fields": fields_data
                }
            ]
        }
    
    def _create_field_entry(self, name, action, auto_generated=False, other=None, fixed=None, remark=None,
                            inherited_from=None):
        """Helper to create a field entry"""
        return {
            "name": name,
            "action": action,
            "other": other,
            "fixed": fixed,
            "remark": remark,
            "auto_generated": auto_generated,
            "inherited_from": inherited_from
        }
    
    def test_not_use_parent_propagates_to_children(self):
        """Test that NOT_USE parent action propagates to all child fields with auto_generated=True"""
        
        # Setup: manual_entries with only parent field set to NOT_USE
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "not_use", auto_generated=False)
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data, 
            self.mock_project, 
            self.mapping_id
        )
        
        # Verify: check that children were added with NOT_USE and auto_generated=True
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should remain unchanged
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["auto_generated"], False)
        
        # Children should be added with NOT_USE and auto_generated=True
        self.assertIn("Practitioner.meta.tag:Origin", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["auto_generated"], True)
        
        self.assertIn("Practitioner.meta.tag:profile:forProfile", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["auto_generated"], True)
    
    def test_empty_parent_propagates_to_children(self):
        """Test that EMPTY parent action propagates to all child fields with auto_generated=True"""
        
        # Setup: manual_entries with only parent field set to EMPTY
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "empty", auto_generated=False)
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: check that children were added with EMPTY and auto_generated=True
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should remain unchanged
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["action"], "empty")
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["auto_generated"], False)
        
        # Children should be added with EMPTY and auto_generated=True
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["action"], "empty")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["auto_generated"], True)
        
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["action"], "empty")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["auto_generated"], True)
    
    def test_parent_action_change_removes_auto_generated_children(self):
        """Test that changing parent action removes auto-generated children but keeps manual ones"""
        
        # Setup: manual_entries with parent and both auto-generated and manual children
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "not_use", auto_generated=False),
            self._create_field_entry("Practitioner.meta.tag:Origin", "not_use", auto_generated=True, 
                                    inherited_from="Practitioner.meta.tag"),
            # manually set
            self._create_field_entry("Practitioner.meta.tag:profile:forProfile", "manual", auto_generated=False),
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Change parent action to USE (non-inheriting action)
        manual_entries_data["entries"][0]["fields"][0]["action"] = "use"
        
        # Execute: propagate parent actions (should cleanup auto-generated children)
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data, 
            self.mock_project, 
            self.mapping_id
        )
        
        # Verify: auto-generated children removed, manual children kept
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should have new action
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["action"], "use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["auto_generated"], False)
        
        # Auto-generated child should be removed
        self.assertNotIn("Practitioner.meta.tag:Origin", fields_by_name)
        
        # Manual child should be kept
        self.assertIn("Practitioner.meta.tag:profile:forProfile", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["action"], "manual")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["auto_generated"], False)
    
    def test_no_propagation_for_non_inheriting_actions(self):
        """Test that non-inheriting actions (USE, MANUAL, etc.) don't propagate to children"""
        
        # Setup: manual_entries with parent field set to USE
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "use", auto_generated=False)
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data, 
            self.mock_project, 
            self.mapping_id
        )
        
        # Verify: no children should be added
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        
        # Only parent field should exist
        self.assertEqual(len(mapping_entry["fields"]), 1)
        self.assertEqual(mapping_entry["fields"][0]["name"], "Practitioner.meta.tag")
        self.assertEqual(mapping_entry["fields"][0]["action"], "use")
    
    def test_multiple_parent_fields_with_different_actions(self):
        """Test handling of multiple parent fields with different actions in same mapping"""
        
        # Setup: manual_entries with multiple parent fields
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "not_use", auto_generated=False),
            self._create_field_entry("Practitioner.identifier", "empty", auto_generated=False),
            self._create_field_entry("Practitioner.name", "use", auto_generated=False),
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Extend field hierarchy for this test
        extended_hierarchy = {
            **self.field_hierarchy,
            "Practitioner.identifier": ["Practitioner.identifier:system"],
            "Practitioner.identifier:system": [],
            "Practitioner.name": ["Practitioner.name:family"],
            "Practitioner.name:family": []
        }
        
        # Add mock fields for new hierarchy
        for field_name in extended_hierarchy.keys():
            if field_name not in self.mock_mapping.fields:
                mock_field = Mock()
                mock_field.name = field_name
                self.mock_mapping.fields[field_name] = mock_field
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data, 
            self.mock_project, 
            self.mapping_id
        )
        
        # Verify: children added only for inheriting actions
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # NOT_USE should have propagated
        self.assertIn("Practitioner.meta.tag:Origin", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["action"], "not_use")
        
        # EMPTY should have propagated
        self.assertIn("Practitioner.identifier:system", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.identifier:system"]["action"], "empty")
        
        # USE should not have propagated
        self.assertNotIn("Practitioner.name:family", fields_by_name)
    
    def test_no_duplicate_children_when_already_exist(self):
        """Test that existing child entries are not duplicated during propagation"""
        
        # Setup: manual_entries with parent and one child already existing
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "not_use", auto_generated=False),
            self._create_field_entry("Practitioner.meta.tag:Origin", "not_use", auto_generated=True),  # already exists
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data, 
            self.mock_project, 
            self.mapping_id
        )
        
        # Verify: existing child is preserved, missing child is added
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Should have parent + 2 children, no duplicates
        self.assertEqual(len(mapping_entry["fields"]), 3)
        
        # Existing child should be preserved
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["auto_generated"], True)
        
        # Missing child should be added
        self.assertIn("Practitioner.meta.tag:profile:forProfile", fields_by_name)
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"]["auto_generated"], True)

    def test_parent_extension_propagates_to_children(self):
        """Test that EXTENSION parent action propagates to all child fields with inherited_from"""
        
        # Setup: manual_entries with parent field set to EXTENSION
        initial_fields = [
            self._create_field_entry("Medication.extension:XYZ", "extension", auto_generated=False)
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Add extension fields to mock project
        extension_fields = [
            "Medication.extension:XYZ",
            "Medication.extension:XYZ.valueCoding", 
            "Medication.extension:XYZ.valueCoding.system"
        ]
        
        # Add mock fields for extension hierarchy
        for field_name in extension_fields:
            if field_name not in self.mock_fields:
                mock_field = Mock()
                mock_field.name = field_name
                self.mock_fields[field_name] = mock_field
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: check that children were added with EXTENSION and inherited_from
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should remain unchanged
        self.assertEqual(fields_by_name["Medication.extension:XYZ"]["action"], "extension")
        self.assertEqual(fields_by_name["Medication.extension:XYZ"]["auto_generated"], False)
        self.assertIsNone(fields_by_name["Medication.extension:XYZ"].get("inherited_from"))
        
        # Children should be added with EXTENSION and inherited_from
        self.assertIn("Medication.extension:XYZ.valueCoding", fields_by_name)
        child_field = fields_by_name["Medication.extension:XYZ.valueCoding"]
        self.assertEqual(child_field["action"], "extension")
        self.assertEqual(child_field["auto_generated"], True)
        self.assertEqual(child_field.get("inherited_from"), "Medication.extension:XYZ")
        
        self.assertIn("Medication.extension:XYZ.valueCoding.system", fields_by_name)
        grandchild_field = fields_by_name["Medication.extension:XYZ.valueCoding.system"]
        self.assertEqual(grandchild_field["action"], "extension")
        self.assertEqual(grandchild_field["auto_generated"], True)
        self.assertEqual(grandchild_field.get("inherited_from"), "Medication.extension:XYZ")

    def test_parent_copy_from_propagates_to_children(self):
        """Test that COPY_FROM parent action propagates to children with other field inheritance"""
        
        # Setup: manual_entries with parent field set to COPY_FROM
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "copy_from", auto_generated=False, other="SomeOtherField")
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: check that children were added with COPY_FROM and inherited other field
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should remain unchanged
        parent_field = fields_by_name["Practitioner.meta.tag"]
        self.assertEqual(parent_field["action"], "copy_from")
        self.assertEqual(parent_field["other"], "SomeOtherField")
        self.assertEqual(parent_field["auto_generated"], False)
        
        # Children should inherit COPY_FROM with same other field
        child_field = fields_by_name["Practitioner.meta.tag:Origin"]
        self.assertEqual(child_field["action"], "copy_from")
        self.assertEqual(child_field["other"], "SomeOtherField")
        self.assertEqual(child_field["auto_generated"], True)
        self.assertEqual(child_field.get("inherited_from"), "Practitioner.meta.tag")

    def test_parent_copy_to_propagates_to_children(self):
        """Test that COPY_TO parent action propagates to children with other field inheritance"""
        
        # Setup: manual_entries with parent field set to COPY_TO  
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "copy_to", auto_generated=False, other="TargetField")
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: check that children were added with COPY_TO and inherited other field
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should remain unchanged
        parent_field = fields_by_name["Practitioner.meta.tag"]
        self.assertEqual(parent_field["action"], "copy_to")
        self.assertEqual(parent_field["other"], "TargetField")
        self.assertEqual(parent_field["auto_generated"], False)
        
        # Children should inherit COPY_TO with same other field
        child_field = fields_by_name["Practitioner.meta.tag:Origin"]
        self.assertEqual(child_field["action"], "copy_to")
        self.assertEqual(child_field["other"], "TargetField")
        self.assertEqual(child_field["auto_generated"], True)
        self.assertEqual(child_field.get("inherited_from"), "Practitioner.meta.tag")

    def test_auto_generated_children_removed_when_parent_action_changes_from_extension(self):
        """Test that auto-generated children are removed when parent changes from EXTENSION to non-inheriting action"""
        
        # Setup: manual_entries with parent and auto-generated children from EXTENSION
        initial_fields = [
            self._create_field_entry("Medication.extension:XYZ", "extension", auto_generated=False),
            self._create_field_entry("Medication.extension:XYZ.valueCoding", "extension", auto_generated=True),
        ]
        # Add inherited_from to the auto-generated child manually since _create_field_entry doesn't support it yet
        initial_fields[1]["inherited_from"] = "Medication.extension:XYZ"
        
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Add extension fields to mock project
        for field_name in ["Medication.extension:XYZ", "Medication.extension:XYZ.valueCoding"]:
            if field_name not in self.mock_mapping.fields:
                mock_field = Mock()
                mock_field.name = field_name
                self.mock_mapping.fields[field_name] = mock_field
        
        # Change parent action to USE (non-inheriting)
        manual_entries_data["entries"][0]["fields"][0]["action"] = "use"
        
        # Execute: propagate parent actions (should cleanup auto-generated children)
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: auto-generated children removed
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should have new action
        self.assertEqual(fields_by_name["Medication.extension:XYZ"]["action"], "use")
        
        # Auto-generated child should be removed
        self.assertNotIn("Medication.extension:XYZ.valueCoding", fields_by_name)

    def test_auto_generated_children_removed_when_parent_action_changes_from_copy_from(self):
        """Test that auto-generated children are removed when parent changes from COPY_FROM to non-inheriting action"""
        
        # Setup: manual_entries with parent and auto-generated children from COPY_FROM
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "copy_from", auto_generated=False, other="SourceField"),
            self._create_field_entry("Practitioner.meta.tag:Origin", "copy_from", auto_generated=True, other="SourceField"),
        ]
        # Add inherited_from to the auto-generated child
        initial_fields[1]["inherited_from"] = "Practitioner.meta.tag"
        
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Change parent action to MANUAL (non-inheriting)
        manual_entries_data["entries"][0]["fields"][0]["action"] = "manual"
        manual_entries_data["entries"][0]["fields"][0]["other"] = None
        
        # Execute: propagate parent actions (should cleanup auto-generated children)
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: auto-generated children removed
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Parent should have new action
        self.assertEqual(fields_by_name["Practitioner.meta.tag"]["action"], "manual")
        
        # Auto-generated child should be removed
        self.assertNotIn("Practitioner.meta.tag:Origin", fields_by_name)

    def test_inherited_from_field_tracks_correct_parent(self):
        """Test that inherited_from field correctly tracks the parent field that triggered inheritance"""
        
        # Setup: multiple parent fields with inheriting actions
        initial_fields = [
            self._create_field_entry("Practitioner.meta.tag", "not_use", auto_generated=False),
            self._create_field_entry("Practitioner.identifier", "extension", auto_generated=False),
        ]
        manual_entries_data = self._create_manual_entries_data(initial_fields)
        
        # Extend field hierarchy for this test
        extended_hierarchy = {
            **self.field_hierarchy,
            "Practitioner.identifier": ["Practitioner.identifier:system"],
            "Practitioner.identifier:system": []
        }
        
        # Add mock fields for new hierarchy
        for field_name in extended_hierarchy.keys():
            if field_name not in self.mock_mapping.fields:
                mock_field = Mock()
                mock_field.name = field_name
                self.mock_mapping.fields[field_name] = mock_field
        
        # Execute: propagate parent actions
        updated_entries = propagate_parent_actions_to_children(
            manual_entries_data,
            self.mock_project,
            self.mapping_id
        )
        
        # Verify: each child tracks its correct parent
        mapping_entry = next(e for e in updated_entries["entries"] if e["id"] == self.mapping_id)
        fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
        
        # Children of Practitioner.meta.tag should inherit from that parent
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"].get("inherited_from"), "Practitioner.meta.tag")
        self.assertEqual(fields_by_name["Practitioner.meta.tag:profile:forProfile"].get("inherited_from"), "Practitioner.meta.tag")
        
        # Children of Practitioner.identifier should inherit from that parent  
        self.assertEqual(fields_by_name["Practitioner.identifier:system"].get("inherited_from"), "Practitioner.identifier")
        
        # Actions should match their respective parents
        self.assertEqual(fields_by_name["Practitioner.meta.tag:Origin"]["action"], "not_use")
        self.assertEqual(fields_by_name["Practitioner.identifier:system"]["action"], "extension")


if __name__ == '__main__':
    unittest.main()