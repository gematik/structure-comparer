"""
Manual Entries ID Mapping Module

This module provides functionality to map legacy mapping IDs to current mapping IDs
based on FHIR resource type context extracted from field names.
"""

import logging
from typing import Dict, Any, Set, List, Tuple

from .data.project import Project

logger = logging.getLogger(__name__)


def extract_resource_type_from_profile_name(profile_name: str) -> str:
    """
    Extract FHIR resource type from profile name.
    
    Args:
        profile_name: The profile name (e.g., "KBV_PR_ERP_Medication_PZN", "EPAMedicationRequest")
        
    Returns:
        The FHIR resource type (e.g., "Medication", "MedicationRequest")
    """
    # Check for specific patterns first (more specific matches first)
    if 'MedicationDispense' in profile_name:
        return 'MedicationDispense'
    elif 'MedicationRequest' in profile_name or 'Prescription' in profile_name:
        return 'MedicationRequest'
    elif 'Medication' in profile_name:
        return 'Medication'
    elif 'Organization' in profile_name:
        return 'Organization'
    elif 'Practitioner' in profile_name:
        return 'Practitioner'
    else:
        logger.warning(f"Unknown resource type in profile name: {profile_name}")
        return 'Unknown'


def extract_fhir_context_from_fields(fields: List[str]) -> Set[str]:
    """
    Extract FHIR resource types from field names.
    
    Args:
        fields: List of field names (e.g., ["MedicationRequest.intent", "Medication.code"])
        
    Returns:
        Set of FHIR resource types found in the field names
    """
    resource_types = set()
    
    for field_name in fields:
        if '.' in field_name:
            # Take the part before the first dot
            resource_type = field_name.split('.')[0]
            resource_types.add(resource_type)
    
    return resource_types


def build_current_mapping_context_map(project: Project) -> Dict[frozenset, str]:
    """
    Build a map from FHIR context signatures to current mapping IDs.
    
    Args:
        project: The current project with mappings
        
    Returns:
        Dictionary mapping frozenset of resource types to mapping ID
    """
    context_to_id = {}
    
    for mapping_id, mapping in project.mappings.items():
        # Extract source resource types
        source_resources = set()
        if mapping.sources:
            for source in mapping.sources:
                resource_type = extract_resource_type_from_profile_name(source.name)
                if resource_type != 'Unknown':
                    source_resources.add(resource_type)
        
        # Extract target resource type
        target_resource = None
        if mapping.target:
            target_resource = extract_resource_type_from_profile_name(mapping.target.name)
        
        # Create context signature (combination of all resource types)
        if source_resources and target_resource and target_resource != 'Unknown':
            # For mapping context, we use all involved resource types
            all_resources = source_resources.copy()
            all_resources.add(target_resource)
            context_signature = frozenset(all_resources)
            
            if context_signature in context_to_id:
                logger.warning(
                    f"Duplicate FHIR context signature {context_signature} for mappings "
                    f"{context_to_id[context_signature]} and {mapping_id}"
                )
            else:
                context_to_id[context_signature] = mapping_id
                logger.debug(f"Mapped context {context_signature} to mapping {mapping_id}")
    
    return context_to_id


def rewrite_manual_entries_ids_by_fhir_context(
    project: Project,
    legacy_data: Dict[str, Any],
    migrated_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Nimmt die Legacy-Rohdaten und die bereits migrierten manual_entries im neuen Format
    und schreibt die Mapping-IDs (`id`) anhand des FHIR-Kontextes auf die aktuellen
    Mapping-IDs des Projekts um.

    Args:
        project: Das aktuelle Project-Objekt (inkl. aktueller Mapping-Liste).
        legacy_data: Die ursprüngliche, aus YAML eingelesene Legacy-Struktur.
                     (Top-Level: legacy_mapping_id -> field_dict)
        migrated_data: Die von `migrate_manual_entries(...)` erzeugte Struktur
                       im neuen Format (mit `entries`-Liste).

    Returns:
        Tuple of:
        - Ein neues Dict im aktuellen Ziel-Format (wie `migrated_data`), bei dem
          die `id`-Felder der `entries` auf aktuelle Mapping-IDs umgeschrieben wurden.
        - Statistiken über die ID-Zuordnung
    """
    logger.info("Starting ID mapping from legacy IDs to current mapping IDs")
    
    # Build context map from current mappings
    context_to_current_id = build_current_mapping_context_map(project)
    logger.info(f"Built context map with {len(context_to_current_id)} current mappings")
    
    # Statistics
    stats = {
        "total_legacy_entries": len(migrated_data.get("entries", [])),
        "mapped_entries": 0,
        "unmapped_entries": 0,
        "warnings": [],
        "mappings": {}  # legacy_id -> current_id
    }
    
    # Create new migrated data with updated IDs
    new_migrated_data = {"entries": []}
    
    for entry in migrated_data.get("entries", []):
        legacy_id = entry.get("id")
        
        if not legacy_id:
            logger.warning("Entry without ID found, skipping")
            continue
            
        # Get legacy field data
        legacy_fields = legacy_data.get(legacy_id, {})
        if not legacy_fields:
            logger.warning(f"No legacy data found for ID {legacy_id}")
            stats["warnings"].append(f"No legacy data found for ID {legacy_id}")
            continue
        
        # Extract FHIR context from legacy field names
        legacy_field_names = list(legacy_fields.keys())
        fhir_context = extract_fhir_context_from_fields(legacy_field_names)
        
        if not fhir_context:
            logger.warning(f"No FHIR context found for legacy ID {legacy_id}")
            stats["warnings"].append(f"No FHIR context found for legacy ID {legacy_id}")
            stats["unmapped_entries"] += 1
            continue
        
        # Find matching current mapping ID
        context_signature = frozenset(fhir_context)
        current_mapping_id = None
        
        # Try exact match first
        if context_signature in context_to_current_id:
            current_mapping_id = context_to_current_id[context_signature]
        else:
            # Try to find a compatible mapping (subset/superset matching)
            compatible_mappings = []
            for current_context, mapping_id in context_to_current_id.items():
                # Check if there's significant overlap
                intersection = context_signature.intersection(current_context)
                if intersection and len(intersection) >= min(len(context_signature), len(current_context)):
                    compatible_mappings.append((mapping_id, current_context, len(intersection)))
            
            if len(compatible_mappings) == 1:
                current_mapping_id = compatible_mappings[0][0]
                logger.info(f"Found compatible mapping for {legacy_id}: {fhir_context} -> {compatible_mappings[0][1]}")
            elif len(compatible_mappings) > 1:
                # Multiple matches - use the one with best overlap
                compatible_mappings.sort(key=lambda x: x[2], reverse=True)
                current_mapping_id = compatible_mappings[0][0]
                logger.warning(
                    f"Multiple compatible mappings for {legacy_id}: {fhir_context}. "
                    f"Using best match: {compatible_mappings[0][1]}"
                )
                stats["warnings"].append(
                    f"Multiple compatible mappings for {legacy_id}: {fhir_context}. "
                    f"Using best match: {compatible_mappings[0][1]}"
                )
        
        if current_mapping_id:
            # Create new entry with updated ID
            new_entry = entry.copy()
            new_entry["id"] = current_mapping_id
            new_migrated_data["entries"].append(new_entry)
            
            stats["mapped_entries"] += 1
            stats["mappings"][legacy_id] = current_mapping_id
            
            logger.info(f"Mapped legacy ID {legacy_id} -> current ID {current_mapping_id} (context: {fhir_context})")
        else:
            logger.warning(f"No matching current mapping found for legacy ID {legacy_id} with context {fhir_context}")
            stats["warnings"].append(f"No matching mapping found for legacy ID {legacy_id} with context {fhir_context}")
            stats["unmapped_entries"] += 1
    
    logger.info(f"ID mapping completed: {stats['mapped_entries']} mapped, {stats['unmapped_entries']} unmapped")
    
    return new_migrated_data, stats