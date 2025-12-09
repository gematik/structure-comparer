"""
Unit tests for the DependencyHandler class.

Tests for Package Dependency Analysis according to packages_dependencies_analysis-spec.md

This module tests:
- Package dependency parsing from package.json
- Recursive dependency resolution
- Cycle detection in dependencies
- Missing dependency detection
- Version mismatch detection
"""

import pytest
from unittest.mock import MagicMock, PropertyMock
from typing import Dict, List, Optional

from structure_comparer.handler.dependency import DependencyHandler
from structure_comparer.model.package import PackageInfo
from structure_comparer.model.package_dependency import (
    DependencyAnalysisResult,
    MissingDependency,
    PackageDependency,
    PackageDependencyInfo,
    VersionMismatch,
)


class MockPackageInfo:
    """Mock PackageInfo for testing."""

    def __init__(
        self,
        name: str,
        version: str,
        dependencies: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.version = version
        self.dependencies = dependencies
        self.title = None
        self.description = None
        self.canonical = None
        self.url = None


class MockPackage:
    """Mock Package class for testing."""

    def __init__(
        self,
        name: str,
        version: str,
        dependencies: Optional[Dict[str, str]] = None,
    ):
        self._name = name
        self._version = version
        self.info = MockPackageInfo(name, version, dependencies) if dependencies is not None else None
        # Also create info without dependencies if no dependencies provided
        if self.info is None:
            self.info = MockPackageInfo(name, version, None)

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version


class MockProject:
    """Mock Project class for testing."""

    def __init__(self, packages: List[MockPackage]):
        self.pkgs = packages


class TestDependencyHandler:
    """Tests for DependencyHandler class."""

    def test_empty_project(self):
        """Test analysis of project with no packages."""
        project = MockProject([])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        assert isinstance(result, DependencyAnalysisResult)
        assert len(result.packages) == 0
        assert len(result.missing_dependencies) == 0
        assert len(result.version_mismatches) == 0
        assert result.analysis_timestamp is not None

    def test_single_package_no_dependencies(self):
        """Test analysis of single package with no dependencies."""
        pkg = MockPackage("test.package", "1.0.0", {})
        project = MockProject([pkg])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        assert len(result.packages) == 1
        assert result.packages[0].package_key == "test.package#1.0.0"
        assert result.packages[0].package_name == "test.package"
        assert result.packages[0].package_version == "1.0.0"
        assert len(result.packages[0].direct_dependencies) == 0
        assert len(result.packages[0].all_dependencies) == 0
        assert len(result.missing_dependencies) == 0

    def test_single_package_with_dependencies(self):
        """Test analysis of single package with dependencies."""
        pkg = MockPackage(
            "test.package",
            "1.0.0",
            {"dep.one": "1.0.0", "dep.two": "2.0.0"},
        )
        project = MockProject([pkg])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        assert len(result.packages) == 1
        pkg_info = result.packages[0]
        assert len(pkg_info.direct_dependencies) == 2
        assert len(pkg_info.all_dependencies) == 2

        # Both dependencies should be missing
        assert len(result.missing_dependencies) == 2
        missing_keys = [m.package_key for m in result.missing_dependencies]
        assert "dep.one#1.0.0" in missing_keys
        assert "dep.two#2.0.0" in missing_keys

    def test_dependency_chain_resolved(self):
        """Test that transitive dependencies are resolved correctly.
        
        A -> B -> C: All dependencies should be found.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        pkg_b = MockPackage("pkg.b", "1.0.0", {"pkg.c": "1.0.0"})
        pkg_c = MockPackage("pkg.c", "1.0.0", {})

        project = MockProject([pkg_a, pkg_b, pkg_c])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # Find pkg_a's dependencies
        pkg_a_info = next(p for p in result.packages if p.package_key == "pkg.a#1.0.0")

        # Direct dependency: only B
        assert len(pkg_a_info.direct_dependencies) == 1
        assert pkg_a_info.direct_dependencies[0].package_key == "pkg.b#1.0.0"

        # All dependencies: B and C (transitive)
        assert len(pkg_a_info.all_dependencies) == 2
        all_dep_keys = [d.package_key for d in pkg_a_info.all_dependencies]
        assert "pkg.b#1.0.0" in all_dep_keys
        assert "pkg.c#1.0.0" in all_dep_keys

        # No missing dependencies
        assert len(result.missing_dependencies) == 0

    def test_missing_transitive_dependency(self):
        """Test detection of missing transitive dependencies.
        
        A -> B -> C (missing): C should be reported as missing.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        pkg_b = MockPackage("pkg.b", "1.0.0", {"pkg.c": "1.0.0"})
        # pkg_c is NOT in the project

        project = MockProject([pkg_a, pkg_b])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # C should be missing
        assert len(result.missing_dependencies) == 1
        missing = result.missing_dependencies[0]
        assert missing.package_key == "pkg.c#1.0.0"
        # It's a direct dependency of B, so is_direct_dependency should reflect
        # that it IS directly required by B (even if transitively by A)
        assert "pkg.b#1.0.0" in missing.required_by

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are handled without infinite loop.
        
        A -> B -> A: Should not cause infinite recursion.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        pkg_b = MockPackage("pkg.b", "1.0.0", {"pkg.a": "1.0.0"})

        project = MockProject([pkg_a, pkg_b])
        handler = DependencyHandler(project)

        # Should not raise or hang
        result = handler.analyze_dependencies()

        assert len(result.packages) == 2
        # No missing dependencies since both exist
        assert len(result.missing_dependencies) == 0

    def test_version_mismatch_detected(self):
        """Test detection of version conflicts.
        
        A requires B@1.0.0, C requires B@2.0.0: Should report mismatch.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        pkg_c = MockPackage("pkg.c", "1.0.0", {"pkg.b": "2.0.0"})
        # Neither version of B is loaded

        project = MockProject([pkg_a, pkg_c])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # Should have version mismatch for pkg.b
        assert len(result.version_mismatches) == 1
        mismatch = result.version_mismatches[0]
        assert mismatch.package_name == "pkg.b"
        assert mismatch.available_version is None  # Not loaded

        # Both versions should be in requirements
        versions = [r.version for r in mismatch.required_versions]
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_version_mismatch_with_available_package(self):
        """Test version mismatch when one version is available.
        
        A requires B@1.0.0, C requires B@2.0.0, B@1.0.0 is loaded.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        pkg_b = MockPackage("pkg.b", "1.0.0", {})  # Version 1.0.0 is loaded
        pkg_c = MockPackage("pkg.c", "1.0.0", {"pkg.b": "2.0.0"})

        project = MockProject([pkg_a, pkg_b, pkg_c])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # Should still report version mismatch
        assert len(result.version_mismatches) == 1
        mismatch = result.version_mismatches[0]
        assert mismatch.package_name == "pkg.b"
        assert mismatch.available_version == "1.0.0"

    def test_direct_vs_transitive_dependency_flag(self):
        """Test that is_direct_dependency flag is set correctly.
        
        A -> B -> C (missing)
        - B is direct dependency of A
        - C is transitive dependency (only direct of B)
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0"})
        # B is not loaded, C would be transitive if B was loaded

        project = MockProject([pkg_a])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # B is missing and is a direct dependency
        missing_b = next(
            (m for m in result.missing_dependencies if m.package_key == "pkg.b#1.0.0"),
            None,
        )
        assert missing_b is not None
        assert missing_b.is_direct_dependency is True

    def test_get_package_dependencies_existing(self):
        """Test getting dependencies for a single existing package."""
        pkg = MockPackage(
            "test.package",
            "1.0.0",
            {"dep.one": "1.0.0"},
        )
        project = MockProject([pkg])
        handler = DependencyHandler(project)

        result = handler.get_package_dependencies("test.package#1.0.0")

        assert result is not None
        assert result.package_key == "test.package#1.0.0"
        assert len(result.direct_dependencies) == 1

    def test_get_package_dependencies_not_found(self):
        """Test getting dependencies for non-existing package."""
        project = MockProject([])
        handler = DependencyHandler(project)

        result = handler.get_package_dependencies("nonexistent#1.0.0")

        assert result is None

    def test_package_info_dependencies_parsing(self):
        """Test that PackageInfo correctly parses dependencies from JSON."""
        json_data = '''
        {
            "name": "test.package",
            "version": "1.0.0",
            "dependencies": {
                "dep.one": "1.0.0",
                "dep.two": "2.0.0"
            }
        }
        '''
        info = PackageInfo.model_validate_json(json_data)

        assert info.name == "test.package"
        assert info.version == "1.0.0"
        assert info.dependencies is not None
        assert info.dependencies == {"dep.one": "1.0.0", "dep.two": "2.0.0"}

    def test_package_info_without_dependencies(self):
        """Test that PackageInfo handles missing dependencies gracefully."""
        json_data = '''
        {
            "name": "test.package",
            "version": "1.0.0"
        }
        '''
        info = PackageInfo.model_validate_json(json_data)

        assert info.name == "test.package"
        assert info.version == "1.0.0"
        assert info.dependencies is None

    def test_real_world_kbv_dependencies(self):
        """Test with realistic KBV package dependency structure.
        
        Simulates:
        - kbv.ita.erp#1.3.2 depends on: hl7.fhir.r4.core@4.0.1, kbv.basis@1.7.0, kbv.ita.for@1.2.0
        - kbv.ita.for#1.2.0 depends on: hl7.fhir.r4.core@4.0.1, kbv.basis@1.7.0
        
        Only kbv.ita.for is loaded, others should be missing.
        """
        kbv_erp = MockPackage(
            "kbv.ita.erp",
            "1.3.2",
            {
                "hl7.fhir.r4.core": "4.0.1",
                "kbv.basis": "1.7.0",
                "kbv.ita.for": "1.2.0",
            },
        )
        kbv_for = MockPackage(
            "kbv.ita.for",
            "1.2.0",
            {
                "hl7.fhir.r4.core": "4.0.1",
                "kbv.basis": "1.7.0",
            },
        )

        project = MockProject([kbv_erp, kbv_for])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # Should have 2 packages
        assert len(result.packages) == 2

        # Missing dependencies: hl7.fhir.r4.core, kbv.basis
        assert len(result.missing_dependencies) == 2
        missing_keys = [m.package_key for m in result.missing_dependencies]
        assert "hl7.fhir.r4.core#4.0.1" in missing_keys
        assert "kbv.basis#1.7.0" in missing_keys

        # Both packages require the same versions, so no version mismatch
        assert len(result.version_mismatches) == 0

    def test_complex_dependency_tree(self):
        """Test a more complex dependency tree.
        
        A -> B, C
        B -> D
        C -> D, E
        D -> F
        
        Only A, B, C loaded. D, E, F should be missing.
        """
        pkg_a = MockPackage("pkg.a", "1.0.0", {"pkg.b": "1.0.0", "pkg.c": "1.0.0"})
        pkg_b = MockPackage("pkg.b", "1.0.0", {"pkg.d": "1.0.0"})
        pkg_c = MockPackage("pkg.c", "1.0.0", {"pkg.d": "1.0.0", "pkg.e": "1.0.0"})

        project = MockProject([pkg_a, pkg_b, pkg_c])
        handler = DependencyHandler(project)

        result = handler.analyze_dependencies()

        # Missing: D, E (F is transitive of D which is missing)
        missing_keys = [m.package_key for m in result.missing_dependencies]
        assert "pkg.d#1.0.0" in missing_keys
        assert "pkg.e#1.0.0" in missing_keys

        # Check A's all_dependencies
        pkg_a_info = next(p for p in result.packages if p.package_key == "pkg.a#1.0.0")
        all_dep_keys = [d.package_key for d in pkg_a_info.all_dependencies]

        # A should see B, C (direct), D, E (transitive via B and C)
        assert "pkg.b#1.0.0" in all_dep_keys
        assert "pkg.c#1.0.0" in all_dep_keys
        assert "pkg.d#1.0.0" in all_dep_keys
        assert "pkg.e#1.0.0" in all_dep_keys


class TestPackageInfoModel:
    """Tests for PackageInfo model dependency parsing."""

    def test_full_package_json(self):
        """Test parsing a complete package.json structure."""
        json_data = '''
        {
            "name": "kbv.ita.erp",
            "version": "1.3.2",
            "description": "Umsetzung der elektronischen Arzneimittelverordnung",
            "author": "Kassenärztliche Bundesvereinigung (KBV)",
            "fhirVersions": ["4.0.1"],
            "jurisdiction": "urn:iso:std:iso:3166#DE",
            "dependencies": {
                "hl7.fhir.r4.core": "4.0.1",
                "kbv.basis": "1.7.0",
                "kbv.ita.for": "1.2.0"
            }
        }
        '''
        info = PackageInfo.model_validate_json(json_data)

        assert info.name == "kbv.ita.erp"
        assert info.version == "1.3.2"
        assert info.description == "Umsetzung der elektronischen Arzneimittelverordnung"
        assert info.dependencies == {
            "hl7.fhir.r4.core": "4.0.1",
            "kbv.basis": "1.7.0",
            "kbv.ita.for": "1.2.0",
        }

    def test_empty_dependencies(self):
        """Test package.json with empty dependencies object."""
        json_data = '''
        {
            "name": "test.package",
            "version": "1.0.0",
            "dependencies": {}
        }
        '''
        info = PackageInfo.model_validate_json(json_data)

        assert info.dependencies == {}
