"""
Unit tests for manual_entries_id_mapping module
"""

import unittest
from unittest.mock import Mock
from structure_comparer.manual_entries_id_mapping import (
    extract_resource_type_from_profile_name,
    extract_fhir_context_from_fields,
    build_current_mapping_context_map,
    rewrite_manual_entries_ids_by_fhir_context
)


class TestManualEntriesIdMapping(unittest.TestCase):
    
    def test_extract_resource_type_from_profile_name(self):
        """Test FHIR resource type extraction from profile names"""
        test_cases = [
            ("KBV_PR_ERP_Medication_PZN", "Medication"),
            ("EPAMedication", "Medication"),
            ("KBV_PR_ERP_Prescription", "MedicationRequest"),
            ("EPAMedicationRequest", "MedicationRequest"),
            ("GEM_ERP_PR_MedicationDispense", "MedicationDispense"),
            ("EPAMedicationDispense", "MedicationDispense"),
            ("KBV_PR_FOR_Organization", "Organization"),
            ("OrganizationDirectory", "Organization"),
            ("KBV_PR_FOR_Practitioner", "Practitioner"),
            ("PractitionerDirectory", "Practitioner"),
            ("SomeUnknownProfile", "Unknown"),
        ]
        
        for profile_name, expected_type in test_cases:
            with self.subTest(profile_name=profile_name):
                result = extract_resource_type_from_profile_name(profile_name)
                self.assertEqual(result, expected_type)
    
    def test_extract_fhir_context_from_fields(self):
        """Test FHIR context extraction from field names"""
        # Test single resource type
        fields = [
            "MedicationRequest.intent",
            "MedicationRequest.extension:Mehrfachverordnung",
            "MedicationRequest.dosageInstruction.extension:Dosierungskennzeichen"
        ]
        result = extract_fhir_context_from_fields(fields)
        self.assertEqual(result, {"MedicationRequest"})
        
        # Test multiple resource types
        fields = [
            "MedicationRequest.intent",
            "Medication.code",
            "Medication.ingredient.strength"
        ]
        result = extract_fhir_context_from_fields(fields)
        self.assertEqual(result, {"MedicationRequest", "Medication"})
        
        # Test single resource type - Organization
        fields = [
            "Organization.name",
            "Organization.identifier"
        ]
        result = extract_fhir_context_from_fields(fields)
        self.assertEqual(result, {"Organization"})
        
        # Test empty fields
        result = extract_fhir_context_from_fields([])
        self.assertEqual(result, set())
        
        # Test fields without dots
        result = extract_fhir_context_from_fields(["invalidfield"])
        self.assertEqual(result, set())
    
    def test_build_current_mapping_context_map(self):
        """Test building context map from current project mappings"""
        # Mock project and mappings
        project = Mock()
        
        # Mock mapping 1: Medication -> Medication
        mapping1 = Mock()
        source1 = Mock()
        source1.name = "KBV_PR_ERP_Medication_PZN"
        mapping1.sources = [source1]
        target1 = Mock()
        target1.name = "EPAMedication"
        mapping1.target = target1
        
        # Mock mapping 2: MedicationRequest -> MedicationRequest
        mapping2 = Mock()
        source2 = Mock()
        source2.name = "KBV_PR_ERP_Prescription"
        mapping2.sources = [source2]
        target2 = Mock()
        target2.name = "EPAMedicationRequest"
        mapping2.target = target2
        
        # Mock mapping 3: Organization -> Organization
        mapping3 = Mock()
        source3 = Mock()
        source3.name = "KBV_PR_FOR_Organization"
        mapping3.sources = [source3]
        target3 = Mock()
        target3.name = "OrganizationDirectory"
        mapping3.target = target3
        
        project.mappings = {
            "mapping-id-1": mapping1,
            "mapping-id-2": mapping2,
            "mapping-id-3": mapping3
        }
        
        result = build_current_mapping_context_map(project)
        
        expected = {
            frozenset({"Medication"}): "mapping-id-1",
            frozenset({"MedicationRequest"}): "mapping-id-2",
            frozenset({"Organization"}): "mapping-id-3"
        }
        
        self.assertEqual(result, expected)
    
    def test_rewrite_manual_entries_ids_by_fhir_context(self):
        """Test complete ID rewriting process"""
        # Mock project
        project = Mock()
        
        # Mock mapping 1: Medication -> Medication
        mapping1 = Mock()
        source1 = Mock()
        source1.name = "KBV_PR_ERP_Medication_PZN"
        mapping1.sources = [source1]
        target1 = Mock()
        target1.name = "EPAMedication"
        mapping1.target = target1
        
        # Mock mapping 2: MedicationRequest -> MedicationRequest
        mapping2 = Mock()
        source2 = Mock()
        source2.name = "KBV_PR_ERP_Prescription"
        mapping2.sources = [source2]
        target2 = Mock()
        target2.name = "EPAMedicationRequest"
        mapping2.target = target2
        
        project.mappings = {
            "current-medication-id": mapping1,
            "current-medicationrequest-id": mapping2
        }
        
        # Legacy data
        legacy_data = {
            "legacy-id-1": {
                "Medication.code": {"classification": "use"},
                "Medication.ingredient.strength": {"classification": "manual"}
            },
            "legacy-id-2": {
                "MedicationRequest.intent": {"classification": "use"},
                "MedicationRequest.extension:Mehrfachverordnung": {"classification": "copy_from"}
            }
        }
        
        # Migrated data (with legacy IDs)
        migrated_data = {
            "entries": [
                {
                    "id": "legacy-id-1",
                    "fields": [
                        {"name": "Medication.code", "action": "use"},
                        {"name": "Medication.ingredient.strength", "action": "manual"}
                    ]
                },
                {
                    "id": "legacy-id-2",
                    "fields": [
                        {"name": "MedicationRequest.intent", "action": "use"},
                        {"name": "MedicationRequest.extension:Mehrfachverordnung", "action": "copy_from"}
                    ]
                }
            ]
        }
        
        result_data, stats = rewrite_manual_entries_ids_by_fhir_context(
            project, legacy_data, migrated_data
        )
        
        # Check that IDs were properly mapped
        self.assertEqual(len(result_data["entries"]), 2)
        
        # Check first entry (Medication)
        entry1 = result_data["entries"][0]
        self.assertEqual(entry1["id"], "current-medication-id")
        
        # Check second entry (MedicationRequest)
        entry2 = result_data["entries"][1]
        self.assertEqual(entry2["id"], "current-medicationrequest-id")
        
        # Check statistics
        self.assertEqual(stats["total_legacy_entries"], 2)
        self.assertEqual(stats["mapped_entries"], 2)
        self.assertEqual(stats["unmapped_entries"], 0)
        self.assertEqual(len(stats["warnings"]), 0)
        
        # Check mapping table
        expected_mappings = {
            "legacy-id-1": "current-medication-id",
            "legacy-id-2": "current-medicationrequest-id"
        }
        self.assertEqual(stats["mappings"], expected_mappings)
    
    def test_rewrite_manual_entries_ids_unmapped_context(self):
        """Test handling of unmapped FHIR contexts"""
        # Mock project with no matching mappings
        project = Mock()
        project.mappings = {}
        
        # Legacy data with unknown context
        legacy_data = {
            "legacy-id-1": {
                "UnknownResource.field": {"classification": "use"}
            }
        }
        
        # Migrated data
        migrated_data = {
            "entries": [
                {
                    "id": "legacy-id-1",
                    "fields": [{"name": "UnknownResource.field", "action": "use"}]
                }
            ]
        }
        
        result_data, stats = rewrite_manual_entries_ids_by_fhir_context(
            project, legacy_data, migrated_data
        )
        
        # Should have no mapped entries
        self.assertEqual(len(result_data["entries"]), 0)
        self.assertEqual(stats["mapped_entries"], 0)
        self.assertEqual(stats["unmapped_entries"], 1)
        self.assertTrue(len(stats["warnings"]) > 0)


if __name__ == "__main__":
    unittest.main()