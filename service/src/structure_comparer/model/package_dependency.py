"""
Models for package dependency analysis.
"""

from datetime import datetime

from pydantic import BaseModel


class PackageDependency(BaseModel):
    """A single package dependency."""

    name: str
    version: str
    package_key: str  # name#version


class PackageDependencyInfo(BaseModel):
    """Dependency information for a package."""

    package_key: str
    package_name: str
    package_version: str
    direct_dependencies: list[PackageDependency]
    all_dependencies: list[PackageDependency]  # including transitive


class MissingDependency(BaseModel):
    """A missing package dependency."""

    package_key: str
    required_by: list[str]
    is_direct_dependency: bool


class VersionRequirement(BaseModel):
    """A version requirement for a package."""

    version: str
    required_by: str


class VersionMismatch(BaseModel):
    """Version conflict for a package."""

    package_name: str
    required_versions: list[VersionRequirement]
    available_version: str | None


class DependencyAnalysisResult(BaseModel):
    """Result of the dependency analysis."""

    packages: list[PackageDependencyInfo]
    missing_dependencies: list[MissingDependency]
    version_mismatches: list[VersionMismatch]
    analysis_timestamp: str

    @classmethod
    def create_empty(cls) -> "DependencyAnalysisResult":
        """Create an empty analysis result."""
        return cls(
            packages=[],
            missing_dependencies=[],
            version_mismatches=[],
            analysis_timestamp=datetime.now().isoformat(),
        )
