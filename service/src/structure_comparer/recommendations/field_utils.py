"""Utility functions for field analysis."""

from typing import Any, Optional


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


def get_field_types(field: Any) -> list[str]:
    """Get the FHIR types for a field.
    
    Args:
        field: The field object
        
    Returns:
        List of FHIR type codes (e.g., ['string'], ['CodeableConcept']), empty if not found
    """
    if field is None:
        return []
    
    # Access the types property if available
    if hasattr(field, 'types'):
        types = field.types
        return types if types is not None else []
    
    return []


def are_types_compatible(source_field: Any, target_field: Any) -> tuple[bool, Optional[str]]:
    """Check if source and target fields have compatible FHIR types.
    
    Args:
        source_field: The source field object
        target_field: The target field object
        
    Returns:
        Tuple of (is_compatible, warning_message):
        - is_compatible: True if types match or are compatible
        - warning_message: Warning message if types don't match, None otherwise
    """
    source_types = get_field_types(source_field)
    target_types = get_field_types(target_field)
    
    # If either field has no types defined, we can't verify - allow it but add a remark
    if not source_types or not target_types:
        if not source_types and not target_types:
            # Both fields have no type information
            return True, None
        elif not target_types:
            return True, "Warning: Target field has no type information."
        else:
            return True, "Warning: Source field has no type information."
    
    # Check if there's any overlap in types
    common_types = set(source_types) & set(target_types)
    
    if common_types:
        # Types are compatible
        return True, None
    else:
        # Types don't match - this is a warning condition
        source_types_str = ", ".join(source_types)
        target_types_str = ", ".join(target_types)
        warning = (
            f"FHIR type mismatch: Source has type(s) [{source_types_str}] "
            f"but target has type(s) [{target_types_str}]."
        )
        return False, warning
