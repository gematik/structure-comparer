"""Utility functions for field name parsing and manipulation."""

from typing import Dict, List, Optional


def field_depth(name: str) -> int:
    """Calculate the depth of a field based on dots and colons.
    
    Args:
        name: The field name (e.g., "Patient.identifier.system")
        
    Returns:
        The depth of the field (number of dots + colons)
    """
    return name.count(".") + name.count(":")


def parent_name(name: str) -> Optional[str]:
    """Extract the parent field name.
    
    Args:
        name: The field name (e.g., "Patient.identifier.system")
        
    Returns:
        The parent field name (e.g., "Patient.identifier") or None if no parent
    """
    dot_index = name.rfind(".")
    colon_index = name.rfind(":")
    split_index = max(dot_index, colon_index)
    if split_index == -1:
        return None
    return name[:split_index]


def child_suffix(field_name: str, parent_field_name: str) -> str:
    """Extract the child suffix from a field name.
    
    Args:
        field_name: The full field name (e.g., "Patient.identifier.system")
        parent_field_name: The parent field name (e.g., "Patient.identifier")
        
    Returns:
        The child suffix (e.g., ".system")
    """
    return field_name[len(parent_field_name):]


def is_polymorphic_type_choice(suffix: str) -> bool:
    """Check if a suffix represents a polymorphic type choice.
    
    Args:
        suffix: The field suffix (e.g., ":valueBoolean", ".system")
        
    Returns:
        True if the suffix represents a polymorphic type choice (e.g., :valueBoolean)
    """
    return suffix.startswith(":value")


def get_direct_children(parent_field_name: str, all_fields: Dict[str, object]) -> List[str]:
    """Get all direct child field names of a parent field.
    
    Args:
        parent_field_name: The parent field name (e.g., "Practitioner.identifier:ANR")
        all_fields: Dictionary mapping field names to field objects
        
    Returns:
        List of direct child field names (e.g., ["Practitioner.identifier:ANR.id", ...])
    """
    children = []
    parent_depth = field_depth(parent_field_name)
    
    for field_name in all_fields.keys():
        # Check if this field is a child of the parent
        if field_name.startswith(parent_field_name + ".") or field_name.startswith(parent_field_name + ":"):
            # Only include direct children (one level deeper)
            if field_depth(field_name) == parent_depth + 1:
                children.append(field_name)
    
    return children
