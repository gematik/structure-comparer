"""
Resolver for recursively resolving profile references in mapping fields.

This module provides functionality to resolve profile references
(fixedUri, fixedCanonical, type[].profile[], type[].targetProfile[])
in mapping fields recursively.
"""

import logging
from typing import TYPE_CHECKING

from ..data.profile import Profile, ProfileField
from ..model.comparison import ComparisonClassification
from ..model.mapping import (
    ProfileResolutionInfo,
    ResolvedMappingField,
    ResolvedMappingFieldsResponse,
    ResolvedProfileFieldInfo,
    ResolutionStats,
    UnresolvedReference,
)

if TYPE_CHECKING:
    from ..data.mapping import Mapping, MappingField
    from ..data.project import Project

logger = logging.getLogger(__name__)


# Non-recursive FHIR resource types that don't have fields to load
NON_RECURSIVE_PATTERNS = [
    '/NamingSystem/',
    '/CodeSystem/',
    '/ValueSet/',
    '/ConceptMap/',
    '/SearchParameter/',
    '/OperationDefinition/',
    '/CapabilityStatement/',
    '/ImplementationGuide/',
    'NamingSystem',
    'CodeSystem',
    'ValueSet'
]


class MappingFieldResolver:
    """Resolves profile references in mapping fields recursively.

    This resolver takes a Mapping and recursively follows profile references
    to load fields from referenced profiles. It supports:
    - fixedUri/fixedCanonical references
    - type[].profile[] references (for .resource fields)
    - type[].targetProfile[] references (for Reference fields)

    The resolver maintains a visited set to prevent infinite loops from
    circular references.
    """

    def __init__(
        self,
        project: "Project",
        max_depth: int = 3
    ):
        """Initialize the resolver.

        Args:
            project: The project containing all profiles
            max_depth: Maximum recursion depth (default: 3)
        """
        self.project = project
        self.max_depth = max_depth
        self.visited: set[str] = set()
        self.profile_cache: dict[str, Profile] = {}
        self.unresolved: list[UnresolvedReference] = []
        self.stats = ResolutionStats()
        self._build_profile_lookup()

    def _build_profile_lookup(self) -> None:
        """Build lookup maps for all profiles in the project."""
        self.profile_by_id: dict[str, Profile] = {}
        self.profile_by_url: dict[str, Profile] = {}

        for pkg in self.project.pkgs:
            for prof in pkg.profiles:
                self.profile_by_id[prof.id] = prof
                if prof.url:
                    self.profile_by_url[prof.url] = prof
                    # Also store without version
                    url_without_version = prof.url.split('|')[0]
                    if url_without_version not in self.profile_by_url:
                        self.profile_by_url[url_without_version] = prof

    def resolve_mapping_fields(
        self,
        mapping: "Mapping"
    ) -> ResolvedMappingFieldsResponse:
        """Resolve all fields in a mapping with recursive profile resolution.

        Args:
            mapping: The mapping to resolve

        Returns:
            ResolvedMappingFieldsResponse containing all resolved fields
        """
        resolved_fields: list[ResolvedMappingField] = []
        self.unresolved = []
        self.visited = set()
        self.stats = ResolutionStats()

        if not mapping.fields:
            return ResolvedMappingFieldsResponse(
                id=mapping.id,
                fields=[],
                unresolved_references=[],
                resolution_stats=self.stats
            )

        # Get source and target profile keys
        source_keys = [p.key for p in mapping.sources] if mapping.sources else []
        target_key = mapping.target.key if mapping.target else None

        # Process each field in the mapping
        for field_name, field in mapping.fields.items():
            resolved = self._resolve_field(
                field=field,
                source_keys=source_keys,
                target_key=target_key,
                depth=0,
                resolved_from=None
            )
            resolved_fields.extend(resolved)

        # Update stats
        self.stats.total_fields = len(resolved_fields)
        self.stats.unresolved_references = len(self.unresolved)
        self.stats.profiles_loaded = list(self.visited)

        return ResolvedMappingFieldsResponse(
            id=mapping.id,
            fields=resolved_fields,
            unresolved_references=self.unresolved,
            resolution_stats=self.stats
        )

    def _resolve_field(
        self,
        field: "MappingField",
        source_keys: list[str],
        target_key: str | None,
        depth: int,
        resolved_from: str | None
    ) -> list[ResolvedMappingField]:
        """Resolve a single field, recursively following references.

        Args:
            field: The mapping field to resolve
            source_keys: Keys of source profiles
            target_key: Key of target profile
            depth: Current recursion depth
            resolved_from: Path of the parent field if this is a resolved child

        Returns:
            List of resolved fields (including child fields from references)
        """
        result: list[ResolvedMappingField] = []

        # Check recursion depth
        if depth > self.max_depth:
            self.stats.max_depth_reached = max(self.stats.max_depth_reached, depth)
            return result

        # Build source profile info
        source_profiles: dict[str, ResolvedProfileFieldInfo | None] = {}
        source_can_expand = False
        source_type_profiles: list[str] = []
        source_ref_types: list[str] = []

        for key in source_keys:
            profile_field = field.profiles.get(key)
            if profile_field is not None:
                info = self._profile_field_to_info(profile_field)
                source_profiles[key] = info
                if info.can_be_expanded:
                    source_can_expand = True
                if info.type_profiles:
                    source_type_profiles.extend(info.type_profiles)
                if info.ref_types:
                    source_ref_types.extend(info.ref_types)
            else:
                source_profiles[key] = None

        # Build target profile info
        target_info: ResolvedProfileFieldInfo | None = None
        target_can_expand = False
        target_type_profiles: list[str] = []
        target_ref_types: list[str] = []

        if target_key:
            target_field = field.profiles.get(target_key)
            if target_field is not None:
                target_info = self._profile_field_to_info(target_field)
                target_can_expand = target_info.can_be_expanded
                target_type_profiles = target_info.type_profiles or []
                target_ref_types = target_info.ref_types or []

        # Create the resolved field
        resolved_field = ResolvedMappingField(
            name=field.name,
            original_name=field.name.split('.')[-1] if '.' in field.name else field.name,
            source_profiles=source_profiles,
            target_profile=target_info,
            classification=(
                field.classification.value
                if hasattr(field.classification, 'value')
                else str(field.classification)
            ),
            issues=[str(i) for i in field.issues] if field.issues else None,
            action=field.action,
            other=field.other,
            fixed=field.fixed,
            actions_allowed=field.actions_allowed,
            action_info=field.action_info,
            evaluation=field.evaluation,
            recommendations=field.recommendations,
            resolved_from=resolved_from,
            resolution_depth=depth,
            referenced_profile_url=None,
            is_expanded=False,
            source_resolution_info=ProfileResolutionInfo(
                can_be_expanded=source_can_expand,
                resolved_profile_id=None,
                type_profiles=source_type_profiles if source_type_profiles else None,
                ref_types=source_ref_types if source_ref_types else None
            ) if source_can_expand else None,
            target_resolution_info=ProfileResolutionInfo(
                can_be_expanded=target_can_expand,
                resolved_profile_id=None,
                type_profiles=target_type_profiles if target_type_profiles else None,
                ref_types=target_ref_types if target_ref_types else None
            ) if target_can_expand else None
        )

        result.append(resolved_field)

        # Recursively resolve references if within depth limit
        if depth < self.max_depth:
            # Collect all resolvable profile URLs
            all_refs = set(
                source_type_profiles + source_ref_types +
                target_type_profiles + target_ref_types
            )

            for ref_url in all_refs:
                if self._is_non_recursive_reference(ref_url):
                    continue

                # Try to resolve the profile
                ref_profile = self._resolve_profile_by_url(ref_url)
                if ref_profile:
                    # Mark as resolved
                    self.stats.resolved_references += 1
                    resolved_field.referenced_profile_url = ref_url

                    # Load child fields from resolved profile
                    child_fields = self._load_profile_fields_as_resolved(
                        profile=ref_profile,
                        source_keys=source_keys,
                        target_key=target_key,
                        path_prefix=field.name,
                        depth=depth + 1,
                        resolved_from=field.name
                    )
                    result.extend(child_fields)
                else:
                    # Record as unresolved
                    # Determine reference type and context
                    is_type_profile = (
                        ref_url in source_type_profiles or
                        ref_url in target_type_profiles
                    )
                    is_source = (
                        ref_url in source_type_profiles or
                        ref_url in source_ref_types
                    )
                    self.unresolved.append(UnresolvedReference(
                        field_path=field.name,
                        reference_url=ref_url,
                        reference_type='type_profile' if is_type_profile else 'ref_type',
                        profile_context='source' if is_source else 'target'
                    ))

        return result

    def _load_profile_fields_as_resolved(
        self,
        profile: Profile,
        source_keys: list[str],
        target_key: str | None,
        path_prefix: str,
        depth: int,
        resolved_from: str
    ) -> list[ResolvedMappingField]:
        """Load fields from a resolved profile and convert to ResolvedMappingField.

        Args:
            profile: The resolved profile
            source_keys: Keys of source profiles
            target_key: Key of target profile
            path_prefix: Prefix to prepend to field paths
            depth: Current recursion depth
            resolved_from: Path of the parent field

        Returns:
            List of resolved fields from the profile
        """
        # Prevent cycles
        visit_key = f"{profile.id}:{path_prefix}"
        if visit_key in self.visited:
            return []
        self.visited.add(visit_key)

        result: list[ResolvedMappingField] = []

        for field_id, field_data in profile.fields.items():
            # Build the full path
            full_path = f"{path_prefix}.{field_data.path}" if path_prefix else field_data.path
            if full_path.startswith('.'):
                full_path = full_path[1:]

            # Create resolved field info for this profile's field
            field_info = self._profile_field_to_info(field_data)

            # For now, we only have this profile's data - source/target distinction
            # needs to come from the original mapping context
            # This is a simplified version - we mark all as the referenced profile
            source_profiles: dict[str, ResolvedProfileFieldInfo | None] = {}
            for key in source_keys:
                # Check if this field exists in the resolved profile context
                source_profiles[key] = field_info

            resolved_field = ResolvedMappingField(
                name=full_path,
                original_name=field_data.path.split('.')[-1] if '.' in field_data.path else field_data.path,
                source_profiles=source_profiles,
                target_profile=field_info,  # Simplified - same for both
                classification=ComparisonClassification.COMPAT.value,  # Default, would need proper comparison
                issues=None,
                action=None,  # No action set for resolved child fields
                other=None,
                fixed=None,
                actions_allowed=[],
                action_info=None,
                evaluation=None,
                recommendations=[],
                resolved_from=resolved_from,
                resolution_depth=depth,
                referenced_profile_url=profile.url,
                is_expanded=False,
                source_resolution_info=ProfileResolutionInfo(
                    can_be_expanded=field_info.can_be_expanded,
                    resolved_profile_id=profile.id,
                    type_profiles=field_info.type_profiles,
                    ref_types=field_info.ref_types
                ) if field_info.can_be_expanded else None,
                target_resolution_info=None
            )

            result.append(resolved_field)

            # Continue recursion if the field has expandable references
            if field_info.can_be_expanded and depth < self.max_depth:
                all_refs = (field_info.type_profiles or []) + (field_info.ref_types or [])
                for ref_url in all_refs:
                    if self._is_non_recursive_reference(ref_url):
                        continue

                    ref_profile = self._resolve_profile_by_url(ref_url)
                    if ref_profile:
                        self.stats.resolved_references += 1
                        child_fields = self._load_profile_fields_as_resolved(
                            profile=ref_profile,
                            source_keys=source_keys,
                            target_key=target_key,
                            path_prefix=full_path,
                            depth=depth + 1,
                            resolved_from=full_path
                        )
                        result.extend(child_fields)

        return result

    def _profile_field_to_info(
        self,
        field: ProfileField
    ) -> ResolvedProfileFieldInfo:
        """Convert a ProfileField to ResolvedProfileFieldInfo.

        Args:
            field: The profile field

        Returns:
            ResolvedProfileFieldInfo with all relevant information
        """
        type_profiles = field.type_profiles if hasattr(field, 'type_profiles') else None
        ref_types = field.ref_types if hasattr(field, 'ref_types') else None
        fixed_value = field.fixed_value if hasattr(field, 'fixed_value') else None
        fixed_value_type = field.fixed_value_type if hasattr(field, 'fixed_value_type') else None

        # Determine if this field can be expanded
        can_expand = False
        if type_profiles:
            can_expand = any(not self._is_non_recursive_reference(p) for p in type_profiles)
        if not can_expand and ref_types:
            can_expand = any(not self._is_non_recursive_reference(r) for r in ref_types)
        if not can_expand and fixed_value and fixed_value_type in ('fixedUri', 'fixedCanonical'):
            fixed_url = str(fixed_value)
            can_expand = (
                ('StructureDefinition' in fixed_url or '/fhir/' in fixed_url) and
                not self._is_non_recursive_reference(fixed_url)
            )

        return ResolvedProfileFieldInfo(
            min=field.min,
            max=field.max,
            must_support=field.must_support,
            types=field.types if hasattr(field, 'types') else None,
            ref_types=ref_types,
            type_profiles=type_profiles,
            cardinality_note=field.cardinality_note if hasattr(field, 'cardinality_note') else None,
            fixed_value=str(fixed_value) if fixed_value else None,
            fixed_value_type=fixed_value_type,
            can_be_expanded=can_expand,
            resolved_profile_id=None
        )

    def _is_non_recursive_reference(self, url: str) -> bool:
        """Check if URL refers to a non-recursive FHIR type."""
        return any(pattern in url for pattern in NON_RECURSIVE_PATTERNS)

    def _resolve_profile_by_url(self, url: str) -> Profile | None:
        """Resolve a profile URL to a Profile object.

        Args:
            url: The profile URL to resolve

        Returns:
            The resolved Profile or None if not found
        """
        # Check cache first
        if url in self.profile_cache:
            return self.profile_cache[url]

        # Direct URL lookup
        if url in self.profile_by_url:
            profile = self.profile_by_url[url]
            self.profile_cache[url] = profile
            return profile

        # Try without version
        url_without_version = url.split('|')[0]
        if url_without_version in self.profile_by_url:
            profile = self.profile_by_url[url_without_version]
            self.profile_cache[url] = profile
            return profile

        # Extract last path segment for ID-based lookup
        url_parts = url.split('/')
        last_part = url_parts[-1] if url_parts else ''
        if last_part and last_part in self.profile_by_id:
            profile = self.profile_by_id[last_part]
            self.profile_cache[url] = profile
            return profile

        # Try partial name match
        for prof in self.profile_by_id.values():
            if prof.name and prof.name in url:
                self.profile_cache[url] = prof
                return prof
            if prof.id and prof.id in url:
                self.profile_cache[url] = prof
                return prof

        return None
