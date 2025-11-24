"""Utility functions for field analysis."""

from typing import Any


def has_zero_cardinality_in_all_sources(field: Any, mapping: Any) -> bool:
    """Check if a field has 0..0 cardinality in ALL source profiles.
    
    Args:
        field: The field to check
        mapping: The mapping object containing source profiles
        
    Returns:
        True if the field has 0..0 cardinality in all source profiles where it exists
    """
    # Get source profile keys from the mapping
    source_keys = []
    if hasattr(mapping, 'sources') and mapping.sources:
        source_keys = [profile.key for profile in mapping.sources]

    # Get all source profiles for this field
    source_profiles_data = []
    for source_key in source_keys:
        profile_field = getattr(field, 'profiles', {}).get(source_key)
        if profile_field is not None:
            source_profiles_data.append(profile_field)

    # If field doesn't exist in any source profile, return False
    if not source_profiles_data:
        return False

    # Check if ALL source profiles have 0..0 cardinality
    return all(
        getattr(pf, 'min', None) == 0 and getattr(pf, 'max', None) == "0"
        for pf in source_profiles_data
    )
