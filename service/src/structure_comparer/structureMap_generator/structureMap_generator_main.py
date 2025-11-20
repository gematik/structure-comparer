"""FHIR StructureMap generation.

This module provides functionality to export mapping actions as FHIR StructureMap
definitions, suitable for FHIR implementation guides.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from structure_comparer.model.mapping_action_models import ActionInfo

if TYPE_CHECKING:
    from structure_comparer.data.mapping import Mapping

    
def build_structuremap(
    mapping: Mapping,
    actions: dict[str, ActionInfo],
    *,
    source_aliases: list[str],
    target_alias: str,
    ruleset_name: str,
) -> str:
    """Build a FHIR StructureMap from mapping actions.

    Args:
        mapping: The mapping object containing field structure
        actions: Map of field_name -> ActionInfo (action details)
        source_aliases: List of aliases for source profiles
            (e.g., ["gematikMedicationDispense", "kvMedicationDispense"])
        target_alias: Alias for the target profile (e.g., "bfarmMedicationDispense")
        ruleset_name: Name of the RuleSet to generate

    Returns:
        JSON string representing a FHIR StructureMap with all available metadata
    """
    
    # Build comprehensive metadata structure
    structuremap_data: dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "generator": "structure-comparer",
            "version": "1.0.0",
            "mapping_info": {
                "id": mapping.id,
                "name": mapping.name,
                "version": mapping.version if hasattr(mapping, 'version') else None,
                "status": mapping.status if hasattr(mapping, 'status') else None,
                "last_updated": (
                    mapping.last_updated.isoformat()
                    if hasattr(mapping, 'last_updated')
                    and mapping.last_updated
                    and hasattr(mapping.last_updated, 'isoformat')
                    else (mapping.last_updated if hasattr(mapping, 'last_updated') else None)
                ),
                "description": mapping.description if hasattr(mapping, 'description') else None,
            },
            "source_profiles": [],
            "target_profile": None,
            "aliases": {
                "sources": source_aliases,
                "target": target_alias,
            },
            "ruleset_name": ruleset_name,
        },
        "field_mappings": [],
    }
    
    # Collect source profile information
    if mapping.sources and len(mapping.sources) > 0:
        for source in mapping.sources:
            source_info = {
                "name": source.name,
                "url": source.url if hasattr(source, 'url') else None,
                "version": source.version if hasattr(source, 'version') else None,
                "profile_key": source.profile_key if hasattr(source, 'profile_key') else None,
                "package": source.package if hasattr(source, 'package') else None,
            }
            structuremap_data["metadata"]["source_profiles"].append(source_info)
    
    # Collect target profile information
    if mapping.target:
        structuremap_data["metadata"]["target_profile"] = {
            "name": mapping.target.name,
            "url": mapping.target.url if hasattr(mapping.target, 'url') else None,
            "version": mapping.target.version if hasattr(mapping.target, 'version') else None,
            "profile_key": mapping.target.profile_key if hasattr(mapping.target, 'profile_key') else None,
            "package": mapping.target.package if hasattr(mapping.target, 'package') else None,
        }
    
    # Collect all field mappings with their actions and metadata
    for field_name, field in mapping.fields.items():
        action_info = actions.get(field_name)
        
        field_mapping = {
            "field_name": field_name,
            "field_metadata": {
                "name": field.name,
                "extension": field.extension if hasattr(field, 'extension') else None,
                "path": field.path if hasattr(field, 'path') else None,
                "type": field.type if hasattr(field, 'type') else None,
            },
            "action": None,
            "profiles": {},
        }
        
        # Add action information if available
        if action_info:
            field_mapping["action"] = {
                "type": action_info.action.value if hasattr(action_info.action, 'value') else str(action_info.action),
                "source": action_info.source.value if hasattr(action_info.source, 'value') else str(action_info.source),
                "user_remark": action_info.user_remark,
                "system_remark": action_info.system_remark,
                "inherited_from": action_info.inherited_from,
                "target_field": action_info.other_value if hasattr(action_info, 'other_value') else None,
                "fixed_value": action_info.fixed_value if hasattr(action_info, 'fixed_value') else None,
            }
        
        # Add profile-specific information for this field
        if hasattr(field, 'profiles') and field.profiles:
            for profile_key, profile_field in field.profiles.items():
                profile_info = {
                    "present": profile_field.present if hasattr(profile_field, 'present') else None,
                    "min": profile_field.min if hasattr(profile_field, 'min') else None,
                    "max": profile_field.max if hasattr(profile_field, 'max') else None,
                    "must_support": profile_field.must_support if hasattr(profile_field, 'must_support') else None,
                    "type": profile_field.type if hasattr(profile_field, 'type') else None,
                    "short": profile_field.short if hasattr(profile_field, 'short') else None,
                    "definition": profile_field.definition if hasattr(profile_field, 'definition') else None,
                    "ref_types": profile_field.ref_types if hasattr(profile_field, 'ref_types') else None,
                }
                field_mapping["profiles"][profile_key] = profile_info
        
        # Add evaluation information if available
        if hasattr(field, 'evaluation'):
            evaluation = field.evaluation
            field_mapping["evaluation"] = {
                "status": (
                    evaluation.mapping_status.value
                    if hasattr(evaluation, 'mapping_status')
                    and hasattr(evaluation.mapping_status, 'value')
                    else None
                ),
                "cardinality_compatible": (
                    evaluation.cardinality_compatible
                    if hasattr(evaluation, 'cardinality_compatible')
                    else None
                ),
                "type_compatible": (
                    evaluation.type_compatible if hasattr(evaluation, 'type_compatible') else None
                ),
                "reasons": [
                    {
                        "severity": (
                            reason.severity.value
                            if hasattr(reason, 'severity') and hasattr(reason.severity, 'value')
                            else None
                        ),
                        "message_key": reason.message_key if hasattr(reason, 'message_key') else None,
                        "details": reason.details if hasattr(reason, 'details') else None,
                    }
                    for reason in evaluation.reasons
                ] if hasattr(evaluation, 'reasons') and evaluation.reasons else [],
            }
        
        structuremap_data["field_mappings"].append(field_mapping)
    
    # Add statistics
    structuremap_data["statistics"] = {
        "total_fields": len(mapping.fields),
        "fields_with_actions": len([f for f in structuremap_data["field_mappings"] if f["action"]]),
        "action_type_counts": {},
    }
    
    # Count action types
    for field_mapping in structuremap_data["field_mappings"]:
        if field_mapping["action"] and field_mapping["action"]["type"]:
            action_type = field_mapping["action"]["type"]
            structuremap_data["statistics"]["action_type_counts"][action_type] = \
                structuremap_data["statistics"]["action_type_counts"].get(action_type, 0) + 1
    
    # Return formatted JSON
    return json.dumps(structuremap_data, indent=2, ensure_ascii=False)
