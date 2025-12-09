"""
Unit tests for the get_resolved_profile_fields function.

Tests for Phase 1: Stabilisierung according to rekursive_Vererbung-spec.md

This module tests:
- Basic profile field resolution
- Recursive fixedUri/fixedCanonical resolution
- Cycle detection in profile references
- Unresolved reference handling
- Empty/missing profile handling
- Non-recursive type exclusion (NamingSystem, CodeSystem, etc.)
"""

import pytest
from unittest.mock import MagicMock
from typing import Dict, Any

from structure_comparer.handler.package import PackageHandler
from structure_comparer.model.profile import (
    ResolvedProfileFieldsResponse,
)


class MockProfile:
    """Mock Profile class for testing."""
    
    def __init__(
        self,
        id: str,
        url: str = "",
        key: str = "",
        name: str = "",
        fields: Dict[str, Any] = None
    ):
        self.id = id
        self.url = url or f"https://example.com/fhir/StructureDefinition/{id}"
        self.key = key or f"{self.url}|1.0.0"
        self.name = name or id
        self.fields = fields or {}


class MockField:
    """Mock field object for testing."""
    
    def __init__(
        self,
        path: str,
        min: int = 0,
        max: str = "1",
        must_support: bool = False,
        types: list = None,
        type_profiles: list = None,
        ref_types: list = None,
        fixed_value: Any = None,
        fixed_value_type: str = None
    ):
        self.path = path
        self.min = min
        self.max = max
        self.must_support = must_support
        self.types = types
        self.type_profiles = type_profiles
        self.ref_types = ref_types
        self.fixed_value = fixed_value
        self.fixed_value_type = fixed_value_type


class MockPackage:
    """Mock Package class for testing."""
    
    def __init__(self, profiles: list):
        self.profiles = profiles


class MockProject:
    """Mock Project class for testing."""
    
    def __init__(self, packages: list):
        self.pkgs = packages


class TestGetResolvedProfileFields:
    """Test suite for get_resolved_profile_fields method."""
    
    @pytest.fixture
    def handler(self):
        """Create a PackageHandler with mocked project handler."""
        project_handler = MagicMock()
        return PackageHandler(project_handler)
    
    def test_empty_profile_ids(self, handler):
        """Test with empty profile IDs list."""
        # Setup mock project with no profiles
        mock_project = MockProject([MockPackage([])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", [])
        
        assert isinstance(result, ResolvedProfileFieldsResponse)
        assert result.resource_fields == []
        assert result.value_fields == []
        assert result.unresolved_references == []
    
    def test_profile_not_found(self, handler):
        """Test when requested profile doesn't exist."""
        mock_project = MockProject([MockPackage([])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields(
            "test-project",
            ["NonExistentProfile"]
        )
        
        assert result.resource_fields == []
        assert result.value_fields == []
        assert result.unresolved_references == []
    
    def test_simple_profile_fields(self, handler):
        """Test loading fields from a simple profile without references."""
        # Create a simple profile with basic fields
        profile = MockProfile(
            id="TestPatient",
            fields={
                "Patient.id": MockField(path="Patient.id", types=["id"]),
                "Patient.name": MockField(path="Patient.name", types=["HumanName"]),
                "Patient.birthDate": MockField(path="Patient.birthDate", types=["date"]),
            }
        )
        
        mock_project = MockProject([MockPackage([profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["TestPatient"])
        
        # All fields should be value fields (no .resource suffix)
        assert len(result.resource_fields) == 0
        assert len(result.value_fields) == 3
        assert result.unresolved_references == []
        
        # Check field paths
        paths = [f.full_path for f in result.value_fields]
        assert "Patient.id" in paths
        assert "Patient.name" in paths
        assert "Patient.birthDate" in paths
    
    def test_resource_field_detection(self, handler):
        """Test that .resource fields are categorized as resource fields."""
        profile = MockProfile(
            id="TestBundle",
            fields={
                "Bundle.entry.resource": MockField(
                    path="Bundle.entry.resource",
                    types=["Resource"]
                ),
                "Bundle.entry.fullUrl": MockField(
                    path="Bundle.entry.fullUrl",
                    types=["uri"]
                ),
            }
        )
        
        mock_project = MockProject([MockPackage([profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["TestBundle"])
        
        # One resource field, one value field
        assert len(result.resource_fields) == 1
        assert len(result.value_fields) == 1
        assert result.resource_fields[0].full_path == "Bundle.entry.resource"
        assert result.resource_fields[0].is_resource_field is True
    
    def test_fixed_uri_resolution(self, handler):
        """Test recursive resolution of fixedUri references."""
        # Parent profile with fixedUri reference
        parent_profile = MockProfile(
            id="ParentBundle",
            fields={
                "Bundle.entry.resource.meta.profile": MockField(
                    path="Bundle.entry.resource.meta.profile",
                    types=["canonical"],
                    fixed_value="https://example.com/fhir/StructureDefinition/ChildMedication",
                    fixed_value_type="fixedUri"
                ),
            }
        )
        
        # Child profile that is referenced
        child_profile = MockProfile(
            id="ChildMedication",
            url="https://example.com/fhir/StructureDefinition/ChildMedication",
            fields={
                "Medication.code": MockField(path="Medication.code", types=["CodeableConcept"]),
                "Medication.status": MockField(path="Medication.status", types=["code"]),
            }
        )
        
        mock_project = MockProject([MockPackage([parent_profile, child_profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["ParentBundle"])
        
        # Should have fields from both profiles
        all_paths = [f.full_path for f in result.value_fields + result.resource_fields]
        
        # Parent field should be included
        assert any("meta.profile" in p for p in all_paths)
        # Child fields should be included
        assert any("Medication.code" in p for p in all_paths)
        assert any("Medication.status" in p for p in all_paths)
    
    def test_type_profiles_resolution(self, handler):
        """Test recursive resolution of type[].profile[] references (Phase 0 fix).
        
        This tests the critical bug fix where .resource fields reference profiles
        via type[].profile[] instead of fixedUri/fixedCanonical.
        """
        # Bundle profile with entry that has type_profiles on .resource field
        bundle_profile = MockProfile(
            id="KBV-PR-ERP-Bundle",
            fields={
                "Bundle.entry:VerordnungArzneimittel.resource": MockField(
                    path=".entry:VerordnungArzneimittel.resource",
                    types=["MedicationRequest"],
                    type_profiles=["https://fhir.kbv.de/StructureDefinition/KBV_PR_ERP_Prescription|1.3"]
                ),
            }
        )
        
        # Referenced profile containing authoredOn field
        prescription_profile = MockProfile(
            id="KBV_PR_ERP_Prescription",
            url="https://fhir.kbv.de/StructureDefinition/KBV_PR_ERP_Prescription",
            key="https://fhir.kbv.de/StructureDefinition/KBV_PR_ERP_Prescription|1.3",
            fields={
                "MedicationRequest.authoredOn": MockField(
                    path=".authoredOn", 
                    types=["dateTime"],
                    must_support=True
                ),
                "MedicationRequest.status": MockField(
                    path=".status", 
                    types=["code"],
                    must_support=True
                ),
                "MedicationRequest.intent": MockField(
                    path=".intent", 
                    types=["code"]
                ),
            }
        )
        
        mock_project = MockProject([MockPackage([bundle_profile, prescription_profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["KBV-PR-ERP-Bundle"])
        
        # Should have the .resource field as a resource field
        assert len(result.resource_fields) == 1
        assert "entry:VerordnungArzneimittel.resource" in result.resource_fields[0].full_path
        
        # Should have fields from the referenced prescription profile
        all_paths = [f.full_path for f in result.value_fields]
        
        # Check that authoredOn field from KBV_PR_ERP_Prescription is included
        authoredOn_paths = [p for p in all_paths if "authoredOn" in p]
        assert len(authoredOn_paths) >= 1, f"Expected authoredOn field, got paths: {all_paths}"
        assert "entry:VerordnungArzneimittel.resource.authoredOn" in authoredOn_paths[0]
        
        # Check other fields are included
        assert any("status" in p for p in all_paths)
        assert any("intent" in p for p in all_paths)

    def test_unresolved_reference_tracking(self, handler):
        """Test that unresolved references are tracked and reported."""
        profile = MockProfile(
            id="TestProfile",
            fields={
                "Bundle.entry.resource.meta.profile": MockField(
                    path="Bundle.entry.resource.meta.profile",
                    types=["canonical"],
                    fixed_value="https://external.com/fhir/StructureDefinition/ExternalProfile",
                    fixed_value_type="fixedCanonical"
                ),
            }
        )
        
        mock_project = MockProject([MockPackage([profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["TestProfile"])
        
        # Should have one unresolved reference
        assert len(result.unresolved_references) == 1
        assert "ExternalProfile" in result.unresolved_references[0]
    
    def test_cycle_detection(self, handler):
        """Test that cyclic references don't cause infinite recursion."""
        # Profile A references Profile B
        profile_a = MockProfile(
            id="ProfileA",
            url="https://example.com/fhir/StructureDefinition/ProfileA",
            fields={
                "ResourceA.reference": MockField(
                    path="ResourceA.reference",
                    types=["Reference"],
                    fixed_value="https://example.com/fhir/StructureDefinition/ProfileB",
                    fixed_value_type="fixedUri"
                ),
            }
        )
        
        # Profile B references Profile A (cycle)
        profile_b = MockProfile(
            id="ProfileB",
            url="https://example.com/fhir/StructureDefinition/ProfileB",
            fields={
                "ResourceB.reference": MockField(
                    path="ResourceB.reference",
                    types=["Reference"],
                    fixed_value="https://example.com/fhir/StructureDefinition/ProfileA",
                    fixed_value_type="fixedUri"
                ),
            }
        )
        
        mock_project = MockProject([MockPackage([profile_a, profile_b])])
        handler.project_handler._get.return_value = mock_project
        
        # Should not raise an exception and should complete
        result = handler.get_resolved_profile_fields("test-project", ["ProfileA"])
        
        # Both profiles' fields should be loaded (but no infinite loop)
        assert isinstance(result, ResolvedProfileFieldsResponse)
        # No unresolved references since both profiles exist
        # (The cycle is handled by the visited set)
    
    def test_non_recursive_type_exclusion(self, handler):
        """Test that NamingSystem, CodeSystem, etc. are not recursively followed."""
        profile = MockProfile(
            id="TestProfile",
            fields={
                "Resource.identifier.system": MockField(
                    path="Resource.identifier.system",
                    types=["uri"],
                    fixed_value="https://example.com/fhir/NamingSystem/TestNamingSystem",
                    fixed_value_type="fixedUri"
                ),
                "Resource.code.system": MockField(
                    path="Resource.code.system",
                    types=["uri"],
                    fixed_value="https://example.com/fhir/CodeSystem/TestCodeSystem",
                    fixed_value_type="fixedUri"
                ),
                "Resource.valueSet": MockField(
                    path="Resource.valueSet",
                    types=["canonical"],
                    fixed_value="https://example.com/fhir/ValueSet/TestValueSet",
                    fixed_value_type="fixedCanonical"
                ),
            }
        )
        
        mock_project = MockProject([MockPackage([profile])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields("test-project", ["TestProfile"])
        
        # These should NOT be in unresolved references because they are
        # explicitly excluded from recursive resolution
        assert "NamingSystem" not in str(result.unresolved_references)
        assert "CodeSystem" not in str(result.unresolved_references)
        assert "ValueSet" not in str(result.unresolved_references)
    
    def test_multiple_profiles(self, handler):
        """Test loading multiple profiles at once."""
        profile1 = MockProfile(
            id="Profile1",
            fields={
                "Resource1.field1": MockField(path="Resource1.field1", types=["string"]),
            }
        )
        
        profile2 = MockProfile(
            id="Profile2",
            fields={
                "Resource2.field2": MockField(path="Resource2.field2", types=["code"]),
            }
        )
        
        mock_project = MockProject([MockPackage([profile1, profile2])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields(
            "test-project",
            ["Profile1", "Profile2"]
        )
        
        # Should have fields from both profiles
        paths = [f.full_path for f in result.value_fields]
        assert len(paths) >= 2
    
    def test_bundle_profile_processed_first(self, handler):
        """Test that Bundle profiles are processed first (sorted)."""
        medication_profile = MockProfile(
            id="MedicationProfile",
            fields={
                "Medication.code": MockField(path="Medication.code", types=["CodeableConcept"]),
            }
        )
        
        bundle_profile = MockProfile(
            id="BundleProfile",
            fields={
                "Bundle.entry": MockField(path="Bundle.entry", types=["BackboneElement"]),
            }
        )
        
        mock_project = MockProject([MockPackage([medication_profile, bundle_profile])])
        handler.project_handler._get.return_value = mock_project
        
        # Pass profiles in non-bundle-first order
        result = handler.get_resolved_profile_fields(
            "test-project",
            ["MedicationProfile", "BundleProfile"]
        )
        
        # Should complete without error
        assert isinstance(result, ResolvedProfileFieldsResponse)
    
    def test_duplicate_field_removal(self, handler):
        """Test that duplicate fields are removed while preserving order."""
        # Two profiles with overlapping fields
        profile1 = MockProfile(
            id="Profile1",
            fields={
                "Resource.id": MockField(path="Resource.id", types=["id"]),
                "Resource.meta": MockField(path="Resource.meta", types=["Meta"]),
            }
        )
        
        profile2 = MockProfile(
            id="Profile2",
            fields={
                "Resource.id": MockField(path="Resource.id", types=["id"]),  # Duplicate
                "Resource.text": MockField(path="Resource.text", types=["Narrative"]),
            }
        )
        
        mock_project = MockProject([MockPackage([profile1, profile2])])
        handler.project_handler._get.return_value = mock_project
        
        result = handler.get_resolved_profile_fields(
            "test-project", 
            ["Profile1", "Profile2"]
        )
        
        # Resource.id should appear only once
        id_fields = [f for f in result.value_fields if f.full_path == "Resource.id"]
        assert len(id_fields) <= 1


class TestIsNonRecursiveReference:
    """Test suite for _is_non_recursive_reference helper method."""
    
    @pytest.fixture
    def handler(self):
        project_handler = MagicMock()
        return PackageHandler(project_handler)
    
    def test_naming_system_excluded(self, handler):
        """Test that NamingSystem URLs are excluded."""
        assert handler._is_non_recursive_reference(
            "https://example.com/fhir/NamingSystem/TestNS"
        ) is True
    
    def test_code_system_excluded(self, handler):
        """Test that CodeSystem URLs are excluded."""
        assert handler._is_non_recursive_reference(
            "https://example.com/fhir/CodeSystem/TestCS"
        ) is True
    
    def test_value_set_excluded(self, handler):
        """Test that ValueSet URLs are excluded."""
        assert handler._is_non_recursive_reference(
            "https://example.com/fhir/ValueSet/TestVS"
        ) is True
    
    def test_structure_definition_not_excluded(self, handler):
        """Test that StructureDefinition URLs are not excluded."""
        assert handler._is_non_recursive_reference(
            "https://example.com/fhir/StructureDefinition/TestSD"
        ) is False
    
    def test_regular_profile_url_not_excluded(self, handler):
        """Test that regular profile URLs are not excluded."""
        assert handler._is_non_recursive_reference(
            "https://example.com/fhir/Patient/123"
        ) is False


class TestExtractRootResourceType:
    """Test suite for _extract_root_resource_type helper method."""
    
    @pytest.fixture
    def handler(self):
        project_handler = MagicMock()
        return PackageHandler(project_handler)
    
    def test_extract_bundle(self, handler):
        """Test extracting Bundle resource type."""
        result = handler._extract_root_resource_type("KBV-PR-ERP-Bundle")
        assert result == "Bundle"
    
    def test_extract_medication(self, handler):
        """Test extracting Medication resource type."""
        result = handler._extract_root_resource_type("KBV-PR-ERP-Medication")
        assert result == "Medication"
    
    def test_extract_patient(self, handler):
        """Test extracting Patient resource type."""
        result = handler._extract_root_resource_type("GEM-PR-Patient")
        assert result == "Patient"
    
    def test_extract_composition(self, handler):
        """Test extracting Composition resource type."""
        result = handler._extract_root_resource_type("KBV-PR-Composition")
        assert result == "Composition"
    
    def test_unknown_resource_type(self, handler):
        """Test with unknown resource type."""
        result = handler._extract_root_resource_type("UnknownProfile")
        assert result == ""


class TestResolveProfileByUrl:
    """Test suite for _resolve_profile_by_url helper method."""
    
    @pytest.fixture
    def handler(self):
        project_handler = MagicMock()
        return PackageHandler(project_handler)
    
    def test_direct_url_match(self, handler):
        """Test direct URL lookup."""
        profile = MockProfile(id="TestProfile", url="https://example.com/fhir/Profile")
        profile_by_id = {"TestProfile": profile}
        profile_by_url = {"https://example.com/fhir/Profile": profile}
        
        result = handler._resolve_profile_by_url(
            "https://example.com/fhir/Profile",
            profile_by_id,
            profile_by_url
        )
        
        assert result == profile
    
    def test_url_without_version(self, handler):
        """Test URL lookup without version."""
        profile = MockProfile(
            id="TestProfile",
            url="https://example.com/fhir/Profile|1.0.0"
        )
        profile_by_id = {"TestProfile": profile}
        profile_by_url = {
            "https://example.com/fhir/Profile|1.0.0": profile,
            "https://example.com/fhir/Profile": profile
        }
        
        result = handler._resolve_profile_by_url(
            "https://example.com/fhir/Profile",
            profile_by_id,
            profile_by_url
        )
        
        assert result == profile
    
    def test_id_based_lookup(self, handler):
        """Test lookup by profile ID from URL path."""
        profile = MockProfile(id="TestProfile", url="https://example.com/fhir/Other")
        profile_by_id = {"TestProfile": profile}
        profile_by_url = {}
        
        result = handler._resolve_profile_by_url(
            "https://example.com/fhir/StructureDefinition/TestProfile",
            profile_by_id,
            profile_by_url
        )
        
        assert result == profile
    
    def test_not_found(self, handler):
        """Test when profile is not found."""
        profile_by_id = {}
        profile_by_url = {}
        
        result = handler._resolve_profile_by_url(
            "https://example.com/fhir/NonExistent",
            profile_by_id,
            profile_by_url
        )
        
        assert result is None
