"""FSH (FHIR Shorthand) export for StructureMap generation.

This module provides functionality to export mapping actions as FHIR StructureMap
definitions in FSH format, suitable for FHIR implementation guides.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .model.mapping_action_models import ActionInfo, ActionSource, ActionType

if TYPE_CHECKING:
    from .data.mapping import Mapping


def build_structuremap_fsh(
    mapping: Mapping,
    actions: dict[str, ActionInfo],
    *,
    source_alias: str,
    target_alias: str,
    ruleset_name: str,
) -> str:
    """Build a FHIR StructureMap in FSH format from mapping actions.
    
    Args:
        mapping: The mapping object containing field structure
        actions: Map of field_name -> ActionInfo (action details)
        source_alias: Alias for the source profile (e.g., "gematikMedicationDispense")
        target_alias: Alias for the target profile (e.g., "bfarmMedicationDispense")
        ruleset_name: Name of the RuleSet to generate
        
    Returns:
        FSH-formatted string representing a StructureMap RuleSet
    """
    lines = []
    
    # RuleSet header
    lines.append(f"RuleSet: {ruleset_name}")
    lines.append(f"// Auto-generated from structure-comparer mapping \"{mapping.name}\"")
    lines.append("* group[+]")
    lines.append(f"  * name = \"{_sanitize_group_name(mapping.name)}\"")
    lines.append("  * typeMode = #none")
    lines.append(f"  * documentation = \"Mapping group generated from structure-comparer mapping {mapping.id}\"")
    lines.append(f"  * insert sd_input({source_alias}, source)")
    lines.append(f"  * insert sd_input({target_alias}, target)")
    lines.append("")
    
    # Generate rules for each field
    for field_name, action_info in actions.items():
        field = mapping.fields.get(field_name)
        if not field:
            continue
            
        # For now, focus on USE actions with compatible fields
        if action_info.action == ActionType.USE and action_info.source in {
            ActionSource.SYSTEM_DEFAULT,
            ActionSource.MANUAL,
        }:
            rule_fsh = _build_copy_rule(
                field_name=field_name,
                source_alias=source_alias,
                target_alias=target_alias,
                action_info=action_info,
            )
            if rule_fsh:
                lines.append(rule_fsh)
                lines.append("")
        else:
            # For non-USE actions, add a TODO comment
            action_type = action_info.action.value
            lines.append(f"// TODO: Handle {action_type} action for field: {field_name}")
            lines.append("")
    
    return "\n".join(lines)


def _build_copy_rule(
    field_name: str,
    source_alias: str,
    target_alias: str,
    action_info: ActionInfo,
) -> str | None:
    """Build a copy rule for a simple USE action.
    
    Args:
        field_name: Full field path (e.g., "MedicationDispense.medication")
        source_alias: Source profile alias
        target_alias: Target profile alias
        action_info: Action information for this field
        
    Returns:
        FSH rule string or None if rule cannot be generated
    """
    # Extract element name from field path
    element_name = _extract_element_name(field_name)
    if not element_name:
        return None
    
    # Sanitize rule name
    rule_name = _sanitize_rule_name(field_name)
    
    # Build the rule
    lines = []
    lines.append("  * rule[+]")
    lines.append(f"    * name = \"{rule_name}\"")
    lines.append(f"    * source.context = \"{source_alias}\"")
    lines.append(f"    * source.element = \"{element_name}\"")
    lines.append(f"    * insert targetCopyVariable({target_alias}, {element_name})")
    
    # Add documentation if available
    doc = action_info.user_remark or action_info.system_remark
    if doc:
        # Escape quotes in documentation
        doc = doc.replace('"', '\\"')
        lines.append(f"    * documentation = \"{doc}\"")
    else:
        lines.append(f"    * documentation = \"Copy {element_name} from source to target\"")
    
    return "\n".join(lines)


def _extract_element_name(field_name: str) -> str:
    """Extract the element name from a field path.
    
    Args:
        field_name: Full field path (e.g., "MedicationDispense.medication.reference")
        
    Returns:
        Element name (e.g., "medication.reference" for nested, "medication" for top-level)
    """
    # Remove the resource type prefix (first segment before first dot)
    parts = field_name.split(".")
    if len(parts) > 1:
        # Return everything after the resource type
        return ".".join(parts[1:])
    return field_name


def _sanitize_rule_name(field_name: str) -> str:
    """Sanitize field name to create a valid FSH rule name.
    
    Args:
        field_name: Full field path
        
    Returns:
        Sanitized rule name suitable for FSH
    """
    # Replace dots and colons with underscores
    sanitized = field_name.replace(".", "_").replace(":", "_")
    # Remove any other problematic characters
    sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in sanitized)
    return sanitized


def _sanitize_group_name(mapping_name: str) -> str:
    """Sanitize mapping name to create a valid FSH group name.
    
    Args:
        mapping_name: Original mapping name
        
    Returns:
        Sanitized group name
    """
    # Remove special characters but keep spaces for readability
    sanitized = "".join(c if c.isalnum() or c in " _-" else "" for c in mapping_name)
    # Collapse multiple spaces
    sanitized = " ".join(sanitized.split())
    return sanitized if sanitized else "MappingGroup"
