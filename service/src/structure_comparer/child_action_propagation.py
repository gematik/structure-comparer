"""
Child Action Propagation Module

Handles automatic propagation of parent mapping actions (NOT_USE, EMPTY) to child fields
with proper auto_generated flag management.
"""

import logging
from typing import Dict, List
from .action import Action
from .data.project import Project


logger = logging.getLogger(__name__)

# Actions that should be inherited by child fields
INHERITING_ACTIONS = {Action.NOT_USE, Action.EMPTY, Action.EXTENSION, Action.COPY_FROM, Action.COPY_TO}


def propagate_parent_actions_to_children(manual_entries_data: dict, project: Project, mapping_id: str) -> dict:
    """
    Propagates vererbende Actions (NOT_USE, EMPTY, EXTENSION, COPY_FROM, COPY_TO) from parent to child fields and
    manages auto-generated child entries when parent actions change.
    
    Args:
        manual_entries_data: The manual entries data structure
        project: Project instance to access mapping field structure
        mapping_id: ID of the mapping to process
    
    Returns:
        Updated manual entries data structure
    """
    logger.warning(f"Step7: propagate_parent_actions_to_children called for mapping_id={mapping_id}")
    logger.warning(f"Step7: Input entries: {manual_entries_data}")
    
    # Find the mapping entry
    mapping_entry = None
    for entry in manual_entries_data.get("entries", []):
        if entry["id"] == mapping_id:
            mapping_entry = entry
            break
    
    if not mapping_entry:
        logger.warning(f"Mapping {mapping_id} not found in manual entries")
        return manual_entries_data
    
    # Get the mapping from project to understand field hierarchy
    mapping = project.get_mapping(mapping_id)
    if not mapping:
        logger.warning(f"Mapping {mapping_id} not found in project")
        return manual_entries_data
    
    # Build field hierarchy map
    field_hierarchy = _build_field_hierarchy(mapping.fields)
    
    # Process the fields
    fields_by_name = {f["name"]: f for f in mapping_entry["fields"]}
    
    # First pass: remove auto-generated children that are no longer needed
    _cleanup_auto_generated_children(fields_by_name, field_hierarchy)
    
    # Second pass: add missing children for inheriting actions
    _add_missing_children(fields_by_name, field_hierarchy)
    
    # Update the fields list
    mapping_entry["fields"] = list(fields_by_name.values())
    
    logger.warning(f"Step7: Output entries: {manual_entries_data}")
    logger.warning(f"Step7: Fields after propagation: {[f['name'] for f in fields_by_name.values()]}")
    
    return manual_entries_data


def _build_field_hierarchy(mapping_fields: Dict) -> Dict[str, List[str]]:
    """
    Build a hierarchy map of parent -> children relationships from mapping fields.
    
    Args:
        mapping_fields: Dictionary of field name -> field object
        
    Returns:
        Dictionary mapping parent field names to lists of child field names
    """
    hierarchy = {}
    field_names = sorted(mapping_fields.keys())
    
    for field_name in field_names:
        hierarchy[field_name] = []
        
        # Find all fields that are children of this field
        for other_field_name in field_names:
            if other_field_name != field_name and _is_child_field(field_name, other_field_name):
                hierarchy[field_name].append(other_field_name)
    return hierarchy


def _is_child_field(parent_name: str, child_name: str) -> bool:
    """
    Check if child_name is a child of parent_name in the field hierarchy.
    This includes both direct and nested children.
    
    Args:
        parent_name: Name of the potential parent field
        child_name: Name of the potential child field
        
    Returns:
        True if child_name is a child of parent_name
    """
    # Check for both ":" and "." as separators for FHIR field hierarchy
    if not (child_name.startswith(parent_name + ":") or child_name.startswith(parent_name + ".")):
        return False
    
    # Any field that starts with parent_name + separator is considered a child
    # This allows for nested inheritance (e.g., parent affects grandchildren too)
    return True


def _cleanup_auto_generated_children(fields_by_name: Dict[str, dict], field_hierarchy: Dict[str, List[str]]) -> None:
    """
    Remove auto-generated children that are no longer needed because their parent
    doesn't have an inheriting action anymore.
    
    Args:
        fields_by_name: Dictionary of field name -> field data (modified in place)
        field_hierarchy: Parent -> children mapping
    """
    fields_to_remove = []
    
    for parent_name, children in field_hierarchy.items():
        parent_field = fields_by_name.get(parent_name)
        
        if not parent_field:
            continue
            
        parent_action = parent_field.get("action")
        has_inheriting_action = parent_action in [action.value for action in INHERITING_ACTIONS]
        
        if not has_inheriting_action:
            # Parent doesn't have inheriting action, remove auto-generated children inherited from this parent
            for child_name in children:
                child_field = fields_by_name.get(child_name)
                if (child_field and
                        child_field.get("auto_generated", False) and
                        child_field.get("inherited_from") == parent_name):
                    fields_to_remove.append(child_name)
    
    # Remove the identified fields
    for field_name in fields_to_remove:
        del fields_by_name[field_name]
        logger.debug(f"Removed auto-generated child field: {field_name}")


def _add_missing_children(fields_by_name: Dict[str, dict], field_hierarchy: Dict[str, List[str]]) -> None:
    """
    Add missing children for parent fields that have inheriting actions.
    
    Args:
        fields_by_name: Dictionary of field name -> field data (modified in place)
        field_hierarchy: Parent -> children mapping
    """
    for parent_name, children in field_hierarchy.items():
        parent_field = fields_by_name.get(parent_name)
        
        if not parent_field:
            continue
            
        parent_action = parent_field.get("action")
        
        if parent_action in [action.value for action in INHERITING_ACTIONS]:
            # Parent has inheriting action, ensure all children have the same action
            for child_name in children:
                if child_name not in fields_by_name:
                    # Create new auto-generated child field
                    child_field = {
                        "name": child_name,
                        "action": parent_action,
                        "other": parent_field.get("other"),  # Inherit other field for COPY actions
                        "fixed": parent_field.get("fixed"),  # Inherit fixed value if any
                        "remark": parent_field.get("remark"),  # Inherit remark if any
                        "auto_generated": True,
                        "inherited_from": parent_name
                    }
                    fields_by_name[child_name] = child_field
                    logger.debug(f"Added auto-generated child field: {child_name} with action: {parent_action}")
                elif (fields_by_name[child_name].get("auto_generated", False) and
                      fields_by_name[child_name].get("inherited_from") == parent_name):
                    # Update existing auto-generated child to match parent action (only if inherited from this parent)
                    child_field = fields_by_name[child_name]
                    child_field["action"] = parent_action
                    child_field["other"] = parent_field.get("other")
                    child_field["fixed"] = parent_field.get("fixed")
                    child_field["remark"] = parent_field.get("remark")
                    logger.debug(f"Updated auto-generated child field: {child_name} to action: {parent_action}")
                # Note: we don't modify manually set children (auto_generated=False)
