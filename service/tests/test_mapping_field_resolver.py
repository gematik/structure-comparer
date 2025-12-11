"""
Unit tests for the MappingFieldResolver class.

Tests for the recursive resolution of profile references in mapping fields.

This module tests:
- Basic field resolution without references
- Recursive resolution of type profiles
- Recursive resolution of ref types (Reference targets)
- Cycle detection
- Max depth enforcement
- Non-recursive type exclusion (CodeSystem, ValueSet, etc.)
- URL-based profile resolution with version handling
- Statistics tracking
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from structure_comparer.resolver.mapping_field_resolver import (
    MappingFieldResolver,
    NON_RECURSIVE_PATTERNS,
)
from structure_comparer.model.mapping import (
    ResolvedMappingFieldsResponse,
    ResolvedMappingField,
    ProfileResolutionInfo,
    ResolutionStats,
    UnresolvedReference,
)
from structure_comparer.model.comparison import ComparisonClassification


class MockProfileField:
    """Mock ProfileField for testing."""

    def __init__(
        self,
        path: str,
        min: int = 0,
        max: str = "1",
        must_support: bool = False,
        types: list[str] | None = None,
        type_profiles: list[str] | None = None,
        ref_types: list[str] | None = None,
        fixed_value: str | None = None,
        fixed_value_type: str | None = None,
        cardinality_note: str | None = None,
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
        self.cardinality_note = cardinality_note


class MockMappingField:
    """Mock MappingField for testing."""

    def __init__(
        self,
        name: str,
        profiles: dict[str, MockProfileField | None] = None,
        classification: ComparisonClassification = ComparisonClassification.COMPAT,
        issues: list | None = None,
        action: str | None = None,
        other: str | None = None,
        fixed: str | None = None,
        actions_allowed: list | None = None,
        action_info: dict | None = None,
        evaluation: dict | None = None,
        recommendations: list | None = None,
    ):
        self.name = name
        self.profiles = profiles or {}
        self.classification = classification
        self.issues = issues or []
        self.action = action
        self.other = other
        self.fixed = fixed
        self.actions_allowed = actions_allowed or []
        self.action_info = action_info
        self.evaluation = evaluation
        self.recommendations = recommendations or []


class MockProfile:
    """Mock Profile for testing."""

    def __init__(
        self,
        id: str,
        url: str = "",
        name: str = "",
        fields: dict[str, MockProfileField] | None = None,
    ):
        self.id = id
        self.url = url or f"https://example.com/fhir/StructureDefinition/{id}"
        self.name = name or id
        self.fields = fields or {}


class MockMapping:
    """Mock Mapping for testing."""

    def __init__(
        self,
        id: str,
        sources: list | None = None,
        target: object | None = None,
        fields: dict[str, MockMappingField] | None = None,
    ):
        self.id = id
        self.sources = sources or []
        self.target = target
        self.fields = fields or {}


class MockProfileRef:
    """Mock profile reference with key."""

    def __init__(self, key: str):
        self.key = key


class MockPackage:
    """Mock Package for testing."""

    def __init__(self, profiles: list[MockProfile] | None = None):
        self.profiles = profiles or []


class MockProject:
    """Mock Project for testing."""

    def __init__(self, packages: list[MockPackage] | None = None):
        self.pkgs = packages or []


class TestMappingFieldResolver:
    """Test suite for MappingFieldResolver."""

    # ========== Initialization Tests ==========

    def test_initialization_with_empty_project(self):
        """Test initialization with a project that has no profiles."""
        project = MockProject([MockPackage([])])
        resolver = MappingFieldResolver(project)

        assert resolver.project == project
        assert resolver.max_depth == 3  # default
        assert resolver.profile_by_id == {}
        assert resolver.profile_by_url == {}

    def test_initialization_builds_profile_lookup(self):
        """Test that initialization builds profile lookup maps."""
        profile1 = MockProfile(
            id="PatientProfile",
            url="https://example.com/fhir/StructureDefinition/PatientProfile|1.0.0"
        )
        profile2 = MockProfile(
            id="OrganizationProfile",
            url="https://example.com/fhir/StructureDefinition/OrganizationProfile"
        )
        project = MockProject([MockPackage([profile1, profile2])])

        resolver = MappingFieldResolver(project)

        assert "PatientProfile" in resolver.profile_by_id
        assert "OrganizationProfile" in resolver.profile_by_id
        # URL with version
        assert "https://example.com/fhir/StructureDefinition/PatientProfile|1.0.0" in resolver.profile_by_url
        # URL without version
        assert "https://example.com/fhir/StructureDefinition/PatientProfile" in resolver.profile_by_url
        assert "https://example.com/fhir/StructureDefinition/OrganizationProfile" in resolver.profile_by_url

    def test_custom_max_depth(self):
        """Test initialization with custom max_depth."""
        project = MockProject([])
        resolver = MappingFieldResolver(project, max_depth=5)

        assert resolver.max_depth == 5

    # ========== Empty Mapping Tests ==========

    def test_resolve_empty_mapping(self):
        """Test resolving a mapping with no fields."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        mapping = MockMapping(id="test-mapping", fields={})
        result = resolver.resolve_mapping_fields(mapping)

        assert isinstance(result, ResolvedMappingFieldsResponse)
        assert result.id == "test-mapping"
        assert result.fields == []
        assert result.unresolved_references == []
        assert result.resolution_stats.total_fields == 0

    def test_resolve_mapping_with_none_fields(self):
        """Test resolving a mapping with fields=None."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        mapping = MockMapping(id="test-mapping", fields=None)
        result = resolver.resolve_mapping_fields(mapping)

        assert result.fields == []

    # ========== Basic Field Resolution Tests ==========

    def test_resolve_simple_field_no_references(self):
        """Test resolving a simple field without profile references."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        source_key = "source-profile|1.0.0"
        target_key = "target-profile|1.0.0"

        source_field = MockProfileField(path="name", min=1, max="1", must_support=True)
        target_field = MockProfileField(path="name", min=0, max="*", must_support=False)

        mapping_field = MockMappingField(
            name="Patient.name",
            profiles={
                source_key: source_field,
                target_key: target_field,
            },
            classification=ComparisonClassification.COMPAT
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=MockProfileRef(target_key),
            fields={"Patient.name": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.fields) == 1
        resolved = result.fields[0]
        assert resolved.name == "Patient.name"
        assert resolved.original_name == "name"
        assert source_key in resolved.source_profiles
        assert resolved.target_profile is not None
        assert resolved.resolution_depth == 0
        assert resolved.resolved_from is None

    def test_resolve_field_with_missing_profile_entry(self):
        """Test resolving a field where source profile entry is None."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        source_key = "source-profile|1.0.0"
        target_key = "target-profile|1.0.0"

        target_field = MockProfileField(path="status", min=1, max="1")

        mapping_field = MockMappingField(
            name="Observation.status",
            profiles={
                source_key: None,  # Missing in source
                target_key: target_field,
            }
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=MockProfileRef(target_key),
            fields={"Observation.status": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.fields) == 1
        resolved = result.fields[0]
        assert resolved.source_profiles[source_key] is None
        assert resolved.target_profile is not None

    # ========== Recursive Resolution Tests ==========

    def test_resolve_field_with_type_profile_reference(self):
        """Test resolving a field that has type_profiles pointing to another profile."""
        # Create a referenced profile
        referenced_profile = MockProfile(
            id="MedicationProfile",
            url="https://example.com/fhir/StructureDefinition/MedicationProfile",
            fields={
                "Medication.code": MockProfileField(path="Medication.code", min=1, max="1"),
                "Medication.status": MockProfileField(path="Medication.status", min=0, max="1"),
            }
        )

        project = MockProject([MockPackage([referenced_profile])])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="medication",
            min=1,
            max="1",
            type_profiles=["https://example.com/fhir/StructureDefinition/MedicationProfile"]
        )

        mapping_field = MockMappingField(
            name="MedicationRequest.medication",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"MedicationRequest.medication": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        # Should have the original field plus expanded child fields
        assert len(result.fields) >= 1
        # Check that child fields were added
        field_names = [f.name for f in result.fields]
        assert "MedicationRequest.medication" in field_names
        # Child fields should have the prefix
        child_fields = [f for f in result.fields if f.resolved_from == "MedicationRequest.medication"]
        assert len(child_fields) == 2  # code and status
        assert result.resolution_stats.resolved_references > 0

    def test_resolve_field_with_ref_types_reference(self):
        """Test resolving a field that has ref_types (Reference target profiles)."""
        referenced_profile = MockProfile(
            id="PatientProfile",
            url="https://example.com/fhir/StructureDefinition/PatientProfile",
            fields={
                "Patient.name": MockProfileField(path="Patient.name", min=0, max="*"),
            }
        )

        project = MockProject([MockPackage([referenced_profile])])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="subject",
            types=["Reference"],
            ref_types=["https://example.com/fhir/StructureDefinition/PatientProfile"]
        )

        mapping_field = MockMappingField(
            name="Observation.subject",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Observation.subject": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.fields) >= 1
        field_names = [f.name for f in result.fields]
        assert "Observation.subject" in field_names

    # ========== Non-Recursive Type Exclusion Tests ==========

    def test_skip_codesystem_reference(self):
        """Test that CodeSystem references are not followed."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="code",
            type_profiles=["https://example.com/fhir/CodeSystem/TestCodes"]
        )

        mapping_field = MockMappingField(
            name="Observation.code",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Observation.code": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        # Should only have the original field, no child fields
        assert len(result.fields) == 1
        assert result.resolution_stats.resolved_references == 0

    def test_skip_valueset_reference(self):
        """Test that ValueSet references are not followed."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="status",
            type_profiles=["https://example.com/fhir/ValueSet/ObservationStatus"]
        )

        mapping_field = MockMappingField(
            name="Observation.status",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Observation.status": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.fields) == 1
        assert result.resolution_stats.resolved_references == 0

    def test_non_recursive_patterns(self):
        """Test that all non-recursive patterns are properly detected."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        for pattern in NON_RECURSIVE_PATTERNS:
            test_url = f"https://example.com/fhir{pattern}/TestResource"
            assert resolver._is_non_recursive_reference(test_url), f"Pattern {pattern} should be non-recursive"

    # ========== Cycle Detection Tests ==========

    def test_cycle_detection_same_profile(self):
        """Test that cycles are detected when visiting the same profile twice."""
        # Profile that references itself indirectly
        self_referencing_profile = MockProfile(
            id="RecursiveProfile",
            url="https://example.com/fhir/StructureDefinition/RecursiveProfile",
            fields={
                "Resource.nested": MockProfileField(
                    path="Resource.nested",
                    type_profiles=["https://example.com/fhir/StructureDefinition/RecursiveProfile"]
                ),
            }
        )

        project = MockProject([MockPackage([self_referencing_profile])])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="root",
            type_profiles=["https://example.com/fhir/StructureDefinition/RecursiveProfile"]
        )

        mapping_field = MockMappingField(
            name="Container.root",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Container.root": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        # Should not hang or crash - cycle detection should stop recursion
        assert result is not None
        # The profile should only be visited once per path
        visit_count = sum(1 for v in resolver.visited if "RecursiveProfile" in v)
        # Due to cycle detection, should be limited
        assert visit_count <= resolver.max_depth + 1

    # ========== Max Depth Tests ==========

    def test_max_depth_enforcement(self):
        """Test that recursion stops at max_depth."""
        # Create a chain of profiles: A -> B -> C -> D
        profile_d = MockProfile(
            id="ProfileD",
            url="https://example.com/fhir/StructureDefinition/ProfileD",
            fields={"D.value": MockProfileField(path="D.value")}
        )
        profile_c = MockProfile(
            id="ProfileC",
            url="https://example.com/fhir/StructureDefinition/ProfileC",
            fields={
                "C.next": MockProfileField(
                    path="C.next",
                    type_profiles=["https://example.com/fhir/StructureDefinition/ProfileD"]
                )
            }
        )
        profile_b = MockProfile(
            id="ProfileB",
            url="https://example.com/fhir/StructureDefinition/ProfileB",
            fields={
                "B.next": MockProfileField(
                    path="B.next",
                    type_profiles=["https://example.com/fhir/StructureDefinition/ProfileC"]
                )
            }
        )
        profile_a = MockProfile(
            id="ProfileA",
            url="https://example.com/fhir/StructureDefinition/ProfileA",
            fields={
                "A.next": MockProfileField(
                    path="A.next",
                    type_profiles=["https://example.com/fhir/StructureDefinition/ProfileB"]
                )
            }
        )

        project = MockProject([MockPackage([profile_a, profile_b, profile_c, profile_d])])

        # With max_depth=2, should not reach D
        resolver = MappingFieldResolver(project, max_depth=2)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="start",
            type_profiles=["https://example.com/fhir/StructureDefinition/ProfileA"]
        )

        mapping_field = MockMappingField(
            name="Root.start",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Root.start": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        # Check that D was not reached
        field_names = [f.name for f in result.fields]
        d_fields = [f for f in field_names if ".D." in f]
        assert len(d_fields) == 0, "ProfileD should not be reached with max_depth=2"

    def test_max_depth_zero_no_recursion(self):
        """Test that max_depth=0 prevents any recursion."""
        referenced_profile = MockProfile(
            id="ReferencedProfile",
            url="https://example.com/fhir/StructureDefinition/ReferencedProfile",
            fields={"Ref.value": MockProfileField(path="Ref.value")}
        )

        project = MockProject([MockPackage([referenced_profile])])
        resolver = MappingFieldResolver(project, max_depth=0)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="reference",
            type_profiles=["https://example.com/fhir/StructureDefinition/ReferencedProfile"]
        )

        mapping_field = MockMappingField(
            name="Root.reference",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Root.reference": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        # Should only have the root field
        assert len(result.fields) == 1
        assert result.fields[0].name == "Root.reference"

    # ========== Unresolved Reference Tracking Tests ==========

    def test_unresolved_reference_tracking(self):
        """Test that unresolved references are properly tracked."""
        project = MockProject([])  # No profiles
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="missing",
            type_profiles=["https://example.com/fhir/StructureDefinition/NonExistentProfile"]
        )

        mapping_field = MockMappingField(
            name="Resource.missing",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Resource.missing": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.unresolved_references) == 1
        unresolved = result.unresolved_references[0]
        assert unresolved.field_path == "Resource.missing"
        assert unresolved.reference_url == "https://example.com/fhir/StructureDefinition/NonExistentProfile"
        assert unresolved.reference_type == "type_profile"
        assert unresolved.profile_context == "source"

    def test_unresolved_ref_type_reference(self):
        """Test that unresolved ref_type references are tracked correctly."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        target_key = "target|1.0.0"
        target_field = MockProfileField(
            path="subject",
            types=["Reference"],
            ref_types=["https://example.com/fhir/StructureDefinition/MissingPatient"]
        )

        mapping_field = MockMappingField(
            name="Observation.subject",
            profiles={target_key: target_field}
        )

        mapping = MockMapping(
            id="test-mapping",
            sources=[],
            target=MockProfileRef(target_key),
            fields={"Observation.subject": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.unresolved_references) == 1
        unresolved = result.unresolved_references[0]
        assert unresolved.reference_type == "ref_type"
        assert unresolved.profile_context == "target"

    # ========== URL Resolution Tests ==========

    def test_resolve_profile_by_url_with_version(self):
        """Test URL resolution with version suffix."""
        profile = MockProfile(
            id="TestProfile",
            url="https://example.com/fhir/StructureDefinition/TestProfile|1.0.0"
        )
        project = MockProject([MockPackage([profile])])
        resolver = MappingFieldResolver(project)

        found = resolver._resolve_profile_by_url(
            "https://example.com/fhir/StructureDefinition/TestProfile|1.0.0"
        )
        assert found is not None
        assert found.id == "TestProfile"

    def test_resolve_profile_by_url_without_version(self):
        """Test URL resolution without version, when profile has version."""
        profile = MockProfile(
            id="TestProfile",
            url="https://example.com/fhir/StructureDefinition/TestProfile|1.0.0"
        )
        project = MockProject([MockPackage([profile])])
        resolver = MappingFieldResolver(project)

        # Should find by URL without version
        found = resolver._resolve_profile_by_url(
            "https://example.com/fhir/StructureDefinition/TestProfile"
        )
        assert found is not None
        assert found.id == "TestProfile"

    def test_resolve_profile_by_id(self):
        """Test URL resolution falling back to ID matching."""
        profile = MockProfile(
            id="MySpecialProfile",
            url="https://example.com/fhir/StructureDefinition/MySpecialProfile"
        )
        project = MockProject([MockPackage([profile])])
        resolver = MappingFieldResolver(project)

        # Should find by ID in URL path
        found = resolver._resolve_profile_by_url(
            "https://other.com/fhir/StructureDefinition/MySpecialProfile"
        )
        assert found is not None
        assert found.id == "MySpecialProfile"

    def test_resolve_profile_caching(self):
        """Test that profile resolution is cached."""
        profile = MockProfile(
            id="CachedProfile",
            url="https://example.com/fhir/StructureDefinition/CachedProfile"
        )
        project = MockProject([MockPackage([profile])])
        resolver = MappingFieldResolver(project)

        url = "https://example.com/fhir/StructureDefinition/CachedProfile"

        # First resolution
        found1 = resolver._resolve_profile_by_url(url)
        assert url in resolver.profile_cache

        # Second resolution should use cache
        found2 = resolver._resolve_profile_by_url(url)
        assert found1 is found2

    # ========== Statistics Tests ==========

    def test_resolution_stats_tracking(self):
        """Test that resolution statistics are properly tracked."""
        profile = MockProfile(
            id="StatsProfile",
            url="https://example.com/fhir/StructureDefinition/StatsProfile",
            fields={
                "Stats.field1": MockProfileField(path="Stats.field1"),
                "Stats.field2": MockProfileField(path="Stats.field2"),
            }
        )
        project = MockProject([MockPackage([profile])])
        resolver = MappingFieldResolver(project)

        source_key = "source|1.0.0"
        source_field = MockProfileField(
            path="ref",
            type_profiles=["https://example.com/fhir/StructureDefinition/StatsProfile"]
        )

        mapping_field = MockMappingField(
            name="Root.ref",
            profiles={source_key: source_field}
        )

        mapping = MockMapping(
            id="stats-test",
            sources=[MockProfileRef(source_key)],
            target=None,
            fields={"Root.ref": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        stats = result.resolution_stats
        assert stats.total_fields == len(result.fields)
        assert stats.resolved_references > 0
        assert "StatsProfile" in str(stats.profiles_loaded)

    # ========== Profile Field Info Tests ==========

    def test_profile_field_to_info_basic(self):
        """Test conversion of ProfileField to ResolvedProfileFieldInfo."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        field = MockProfileField(
            path="test",
            min=1,
            max="*",
            must_support=True,
            types=["string", "code"],
            cardinality_note="At least one required"
        )

        info = resolver._profile_field_to_info(field)

        assert info.min == 1
        assert info.max == "*"
        assert info.must_support is True
        assert info.types == ["string", "code"]
        assert info.cardinality_note == "At least one required"
        assert info.can_be_expanded is False  # No profile references

    def test_profile_field_to_info_with_type_profiles(self):
        """Test that fields with type_profiles can be expanded."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        field = MockProfileField(
            path="medication",
            type_profiles=["https://example.com/fhir/StructureDefinition/Medication"]
        )

        info = resolver._profile_field_to_info(field)

        assert info.can_be_expanded is True
        assert info.type_profiles == ["https://example.com/fhir/StructureDefinition/Medication"]

    def test_profile_field_to_info_with_fixed_canonical(self):
        """Test that fields with fixedCanonical pointing to StructureDefinition can be expanded."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        field = MockProfileField(
            path="profile",
            fixed_value="https://example.com/fhir/StructureDefinition/Patient",
            fixed_value_type="fixedCanonical"
        )

        info = resolver._profile_field_to_info(field)

        assert info.can_be_expanded is True
        assert info.fixed_value == "https://example.com/fhir/StructureDefinition/Patient"
        assert info.fixed_value_type == "fixedCanonical"

    def test_profile_field_not_expandable_with_valueset_fixed_canonical(self):
        """Test that fixedCanonical to ValueSet is not expandable."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        field = MockProfileField(
            path="valueSet",
            fixed_value="https://example.com/fhir/ValueSet/Codes",
            fixed_value_type="fixedCanonical"
        )

        info = resolver._profile_field_to_info(field)

        # ValueSet should be excluded
        assert info.can_be_expanded is False

    # ========== Multiple Sources Tests ==========

    def test_resolve_with_multiple_sources(self):
        """Test resolution with multiple source profiles."""
        project = MockProject([])
        resolver = MappingFieldResolver(project)

        source_key_1 = "source1|1.0.0"
        source_key_2 = "source2|1.0.0"
        target_key = "target|1.0.0"

        source_field_1 = MockProfileField(path="name", min=1, max="1")
        source_field_2 = MockProfileField(path="name", min=0, max="*")
        target_field = MockProfileField(path="name", min=1, max="*")

        mapping_field = MockMappingField(
            name="Resource.name",
            profiles={
                source_key_1: source_field_1,
                source_key_2: source_field_2,
                target_key: target_field,
            }
        )

        mapping = MockMapping(
            id="multi-source-test",
            sources=[MockProfileRef(source_key_1), MockProfileRef(source_key_2)],
            target=MockProfileRef(target_key),
            fields={"Resource.name": mapping_field}
        )

        result = resolver.resolve_mapping_fields(mapping)

        assert len(result.fields) == 1
        resolved = result.fields[0]
        assert source_key_1 in resolved.source_profiles
        assert source_key_2 in resolved.source_profiles
        assert resolved.source_profiles[source_key_1].min == 1
        assert resolved.source_profiles[source_key_2].min == 0


class TestNonRecursivePatterns:
    """Test the NON_RECURSIVE_PATTERNS constant."""

    def test_patterns_include_common_terminology_types(self):
        """Test that common terminology resources are excluded."""
        assert any('CodeSystem' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('ValueSet' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('NamingSystem' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('ConceptMap' in p for p in NON_RECURSIVE_PATTERNS)

    def test_patterns_include_common_definition_types(self):
        """Test that common definition resources are excluded."""
        assert any('SearchParameter' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('OperationDefinition' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('CapabilityStatement' in p for p in NON_RECURSIVE_PATTERNS)
        assert any('ImplementationGuide' in p for p in NON_RECURSIVE_PATTERNS)
