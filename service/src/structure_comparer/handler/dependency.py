"""
Handler for package dependency analysis.
Recursively analyzes package dependencies and identifies missing packages.
"""

import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple

from ..data.package import Package
from ..data.project import Project
from ..model.package_dependency import (
    DependencyAnalysisResult,
    MissingDependency,
    PackageDependency,
    PackageDependencyInfo,
    VersionMismatch,
    VersionRequirement,
)

logger = logging.getLogger(__name__)

# Maximum recursion depth to prevent infinite loops
MAX_RECURSION_DEPTH = 20


class DependencyHandler:
    """Handler for analyzing package dependencies in a project."""

    def __init__(self, project: Project):
        self.project = project
        # Lookup maps for fast package access
        self._package_by_key: Dict[str, Package] = {}
        self._package_by_name: Dict[str, List[Package]] = {}
        self._build_package_lookups()

    def _build_package_lookups(self) -> None:
        """Build lookup maps for fast package access by key and name."""
        for pkg in self.project.pkgs:
            if pkg.name and pkg.version:
                key = f"{pkg.name}#{pkg.version}"
                self._package_by_key[key] = pkg

                if pkg.name not in self._package_by_name:
                    self._package_by_name[pkg.name] = []
                self._package_by_name[pkg.name].append(pkg)

        logger.debug(
            f"Built package lookups: {len(self._package_by_key)} packages by key, "
            f"{len(self._package_by_name)} unique package names"
        )

    def analyze_dependencies(self) -> DependencyAnalysisResult:
        """
        Analyze all package dependencies recursively.

        Returns:
            DependencyAnalysisResult containing:
            - packages: List of all packages with their dependencies
            - missing_dependencies: List of packages that are required but not loaded
            - version_mismatches: List of packages with conflicting version requirements
        """
        packages_info: List[PackageDependencyInfo] = []
        # Track all required packages: package_key -> set of packages requiring it
        all_required: Dict[str, Set[str]] = {}
        # Track all direct dependencies: package_key -> set of packages requiring it directly
        direct_required: Dict[str, Set[str]] = {}
        # Track version requirements: package_name -> list of (version, required_by)
        version_requirements: Dict[str, List[Tuple[str, str]]] = {}

        for pkg in self.project.pkgs:
            if not pkg.name or not pkg.version:
                continue

            pkg_key = f"{pkg.name}#{pkg.version}"

            # Get direct dependencies from package.json
            direct_deps = self._get_direct_dependencies(pkg)

            # Track direct dependencies
            for dep in direct_deps:
                if dep.package_key not in direct_required:
                    direct_required[dep.package_key] = set()
                direct_required[dep.package_key].add(pkg_key)

                # Track version requirements
                if dep.name not in version_requirements:
                    version_requirements[dep.name] = []
                version_requirements[dep.name].append((dep.version, pkg_key))

            # Resolve all dependencies recursively
            visited: Set[str] = set()
            all_deps = self._resolve_dependencies_recursive(
                pkg, visited=visited, depth=0, path=[pkg_key]
            )

            # Track all dependencies (including transitive)
            for dep in all_deps:
                if dep.package_key not in all_required:
                    all_required[dep.package_key] = set()
                all_required[dep.package_key].add(pkg_key)

                # Track version requirements for transitive deps too
                if dep.name not in version_requirements:
                    version_requirements[dep.name] = []
                # Only add if not already tracked with same version from same package
                existing = [
                    (v, r) for v, r in version_requirements[dep.name] if v == dep.version
                ]
                if not any(r == pkg_key for _, r in existing):
                    version_requirements[dep.name].append((dep.version, pkg_key))

            packages_info.append(
                PackageDependencyInfo(
                    package_key=pkg_key,
                    package_name=pkg.name,
                    package_version=pkg.version,
                    direct_dependencies=direct_deps,
                    all_dependencies=all_deps,
                )
            )

        # Find missing dependencies
        missing_deps = self._find_missing_dependencies(all_required, direct_required)

        # Detect version mismatches
        version_mismatches = self._detect_version_mismatches(version_requirements)

        return DependencyAnalysisResult(
            packages=packages_info,
            missing_dependencies=missing_deps,
            version_mismatches=version_mismatches,
            analysis_timestamp=datetime.now().isoformat(),
        )

    def _get_direct_dependencies(self, pkg: Package) -> List[PackageDependency]:
        """
        Get direct dependencies from a package's package.json.

        Args:
            pkg: The package to get dependencies from

        Returns:
            List of PackageDependency objects
        """
        dependencies: List[PackageDependency] = []

        if pkg.info and pkg.info.dependencies:
            for name, version in pkg.info.dependencies.items():
                dep_key = f"{name}#{version}"
                dependencies.append(
                    PackageDependency(name=name, version=version, package_key=dep_key)
                )

        return dependencies

    def _resolve_dependencies_recursive(
        self,
        pkg: Package,
        visited: Set[str],
        depth: int,
        path: List[str],
    ) -> List[PackageDependency]:
        """
        Recursively resolve all dependencies for a package.

        Args:
            pkg: The package to resolve dependencies for
            visited: Set of already visited package keys (for cycle detection)
            depth: Current recursion depth
            path: Current dependency path (for debugging)

        Returns:
            List of all dependencies (direct and transitive)
        """
        if depth > MAX_RECURSION_DEPTH:
            logger.warning(
                f"Max recursion depth reached at path: {' -> '.join(path)}"
            )
            return []

        all_deps: List[PackageDependency] = []
        seen_keys: Set[str] = set()  # Avoid duplicates in result

        direct_deps = self._get_direct_dependencies(pkg)

        for dep in direct_deps:
            # Add direct dependency if not already in result
            if dep.package_key not in seen_keys:
                all_deps.append(dep)
                seen_keys.add(dep.package_key)

            # Check if we've already visited this package (cycle detection)
            if dep.package_key in visited:
                logger.debug(
                    f"Cycle detected: {dep.package_key} already in path {' -> '.join(path)}"
                )
                continue

            # Try to find the dependency package in the project
            dep_pkg = self._package_by_key.get(dep.package_key)

            if dep_pkg:
                # Mark as visited and recurse
                visited.add(dep.package_key)
                transitive_deps = self._resolve_dependencies_recursive(
                    dep_pkg,
                    visited=visited,
                    depth=depth + 1,
                    path=path + [dep.package_key],
                )

                # Add transitive dependencies
                for trans_dep in transitive_deps:
                    if trans_dep.package_key not in seen_keys:
                        all_deps.append(trans_dep)
                        seen_keys.add(trans_dep.package_key)

        return all_deps

    def _find_missing_dependencies(
        self,
        all_required: Dict[str, Set[str]],
        direct_required: Dict[str, Set[str]],
    ) -> List[MissingDependency]:
        """
        Identify packages that are required but not loaded in the project.

        Args:
            all_required: Map of package_key -> set of packages requiring it
            direct_required: Map of package_key -> set of packages requiring it directly

        Returns:
            List of MissingDependency objects
        """
        missing: List[MissingDependency] = []

        for pkg_key, required_by in all_required.items():
            if pkg_key not in self._package_by_key:
                is_direct = pkg_key in direct_required
                missing.append(
                    MissingDependency(
                        package_key=pkg_key,
                        required_by=sorted(list(required_by)),
                        is_direct_dependency=is_direct,
                    )
                )

        # Sort by package_key for consistent output
        missing.sort(key=lambda m: m.package_key)

        return missing

    def _detect_version_mismatches(
        self,
        version_requirements: Dict[str, List[Tuple[str, str]]],
    ) -> List[VersionMismatch]:
        """
        Detect packages where different versions are required.

        Args:
            version_requirements: Map of package_name -> list of (version, required_by)

        Returns:
            List of VersionMismatch objects
        """
        mismatches: List[VersionMismatch] = []

        for pkg_name, requirements in version_requirements.items():
            # Get unique versions required
            unique_versions = set(version for version, _ in requirements)

            if len(unique_versions) > 1:
                # Multiple versions required - this is a mismatch
                available = None
                if pkg_name in self._package_by_name:
                    # Use the first available version
                    available = self._package_by_name[pkg_name][0].version

                # Build version requirements list
                version_reqs = [
                    VersionRequirement(version=version, required_by=required_by)
                    for version, required_by in requirements
                ]

                mismatches.append(
                    VersionMismatch(
                        package_name=pkg_name,
                        required_versions=version_reqs,
                        available_version=available,
                    )
                )

        # Sort by package name for consistent output
        mismatches.sort(key=lambda m: m.package_name)

        return mismatches

    def get_package_dependencies(self, package_id: str) -> PackageDependencyInfo | None:
        """
        Get dependency information for a single package.

        Args:
            package_id: The package identifier (name#version)

        Returns:
            PackageDependencyInfo or None if package not found
        """
        pkg = self._package_by_key.get(package_id)
        if not pkg:
            return None

        direct_deps = self._get_direct_dependencies(pkg)

        visited: Set[str] = set()
        all_deps = self._resolve_dependencies_recursive(
            pkg, visited=visited, depth=0, path=[package_id]
        )

        return PackageDependencyInfo(
            package_key=package_id,
            package_name=pkg.name or "",
            package_version=pkg.version or "",
            direct_dependencies=direct_deps,
            all_dependencies=all_deps,
        )
