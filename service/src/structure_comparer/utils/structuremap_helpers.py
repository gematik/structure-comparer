"""Helper functions for StructureMap export operations.

This module contains utility functions for:
- Sanitizing names for use in file systems
- Generating safe folder and file names for mappings
- Creating download filenames
"""

import re


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize a mapping name to be safe for use as a folder name.
    Removes or replaces characters that are problematic in file systems.
    
    Args:
        name: The original mapping name
        
    Returns:
        A sanitized version safe for use as a folder name
        
    Examples:
        >>> sanitize_folder_name("Mapping: A|1.0 -> B|2.0")
        'Mapping_A_v1.0_to_B_v2.0'
    """
    # Replace arrow and pipe symbols FIRST before regex replacement
    sanitized = name.replace('->', '_to_')
    sanitized = sanitized.replace('|', '_v')
    
    # Then replace problematic characters with underscores
    # Keep alphanumeric, spaces, hyphens, underscores, periods, and commas
    sanitized = re.sub(r'[<>:"/\\?*\x00-\x1f]', '_', sanitized)
    
    # Replace multiple spaces or underscores with single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    
    # Remove leading/trailing underscores and periods
    sanitized = sanitized.strip('_.')
    
    # Limit length to avoid filesystem issues (max 200 chars)
    if len(sanitized) > 200:
        sanitized = sanitized[:200].rstrip('_.')
    
    return sanitized


def get_safe_mapping_folder_name(mapping, mapping_id: str) -> str:
    """
    Get a safe folder name for a mapping based on its name.
    
    Args:
        mapping: The mapping object (with optional 'name' attribute)
        mapping_id: The mapping ID as fallback
        
    Returns:
        A sanitized folder name
        
    Examples:
        >>> class Mapping:
        ...     name = "My Mapping -> Target"
        >>> get_safe_mapping_folder_name(Mapping(), "abc-123")
        'My_Mapping_to_Target'
    """
    mapping_name = getattr(mapping, 'name', None) or f"mapping_{mapping_id}"
    return sanitize_folder_name(mapping_name)


def get_safe_mapping_filename(mapping, mapping_id: str) -> str:
    """
    Get a safe filename for a mapping ZIP download including version.
    
    Args:
        mapping: The mapping object (with optional 'name' and 'version' attributes)
        mapping_id: The mapping ID as fallback
        
    Returns:
        A sanitized filename with version suffix
        
    Examples:
        >>> class Mapping:
        ...     name = "My Mapping"
        ...     version = "1.0"
        >>> get_safe_mapping_filename(Mapping(), "abc-123")
        'My_Mapping_v1.0_structuremaps.zip'
    """
    mapping_name = getattr(mapping, 'name', None) or f"mapping_{mapping_id}"
    mapping_version = getattr(mapping, 'version', None) or "v1.0"
    safe_name = sanitize_folder_name(mapping_name)
    return f"{safe_name}_v{mapping_version}_structuremaps.zip"


def get_safe_project_filename(project, project_key: str) -> str:
    """
    Get a safe filename for a project-wide ZIP download.
    
    Args:
        project: The project object (with optional 'name' attribute)
        project_key: The project key as fallback
        
    Returns:
        A sanitized filename for the project download
        
    Examples:
        >>> class Project:
        ...     name = "My Project"
        >>> get_safe_project_filename(Project(), "project-key")
        'My_Project_all_structuremaps.zip'
    """
    project_name = getattr(project, 'name', None) or project_key
    safe_project_name = sanitize_folder_name(project_name)
    return f"{safe_project_name}_all_structuremaps.zip"


def alias_from_profile(profile, fallback: str) -> str:
    """
    Extract a safe alias from a profile object.
    
    Tries to get the profile name, id, or url and cleans it to only contain
    alphanumeric characters for use as an alias.
    
    Args:
        profile: The profile object
        fallback: Fallback value if no suitable attribute is found
        
    Returns:
        A cleaned alphanumeric string suitable as an alias
        
    Examples:
        >>> class Profile:
        ...     name = "My-Profile_123"
        >>> alias_from_profile(Profile(), "default")
        'MyProfile123'
    """
    text = getattr(profile, "name", None)
    if not text:
        text = getattr(profile, "id", None) or getattr(profile, "url", None) or ""
    cleaned = "".join(ch for ch in text if ch.isalnum())
    return cleaned or fallback
