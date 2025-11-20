"""
Migration utilities for manual_entries.yaml files.

This module provides functions to migrate legacy manual_entries.yaml formats
to the current internal structure.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Mapping from legacy classification to new action enum values
CLASSIFICATION_TO_ACTION = {
    "use": "use",
    "not_use": "not_use",
    "empty": "empty",
    "fixed": "fixed",
    "copy_from": "copy_from",
    "copy_to": "copy_to",
    "manual": "manual",
    # medication_service is deprecated - migrate to manual
    "medication_service": "manual",
}


def _is_new_format(data: Dict[str, Any]) -> bool:
    """
    Check if the data is already in the new format.
    
    New format has a top-level 'entries' key containing a list.
    Legacy format has mapping UUIDs as top-level keys.
    """
    if "entries" in data and isinstance(data["entries"], list):
        # Check if entries contain the expected structure
        if not data["entries"]:  # Empty list is valid new format
            return True
        # Check first entry for new format structure
        first_entry = data["entries"][0]
        return isinstance(first_entry, dict) and "id" in first_entry and "fields" in first_entry
    return False


def _migrate_field(field_name: str, field_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate a single field from legacy to new format.
    
    Args:
        field_name: The field name (e.g., "MedicationRequest.intent")
        field_config: Legacy field configuration
        
    Returns:
        Dictionary representing the field in new format
        
    Raises:
        ValueError: If field_config is invalid or contains unknown classification
    """
    if not isinstance(field_config, dict):
        raise ValueError(f"Field config for '{field_name}' must be a dictionary")
    
    if "classification" not in field_config:
        raise ValueError(f"Field '{field_name}' missing required 'classification' key")
    
    classification = field_config["classification"]
    if classification not in CLASSIFICATION_TO_ACTION:
        raise ValueError(f"Unknown classification '{classification}' for field '{field_name}'")
    
    # Base new field structure
    new_field = {
        "name": field_name,
        "action": CLASSIFICATION_TO_ACTION[classification]
    }
    
    # Handle 'extra' field mapping based on classification
    if "extra" in field_config:
        extra_value = field_config["extra"]
        
        if classification == "fixed":
            # For FIXED action, extra contains the fixed value
            new_field["fixed"] = extra_value
        elif classification in ("copy_from", "copy_to"):
            # For COPY_FROM/COPY_TO actions, extra contains the other field reference
            new_field["other"] = extra_value
        # For other classifications, extra is ignored (as per requirements)
    
    # Handle remark field - direct copy if present
    if "remark" in field_config:
        new_field["remark"] = field_config["remark"]
    # If medication_service was migrated to manual, add default remark if none exists
    elif classification == "medication_service":
        new_field["remark"] = "Property will be set by medication_service"
    
    return new_field


def migrate_manual_entries(legacy_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrates legacy manual_entries.yaml data to the current format.
    
    Args:
        legacy_data: Dictionary containing the parsed legacy YAML data
        
    Returns:
        Dictionary in the current ManualEntries format
        
    Raises:
        ValueError: If the legacy data cannot be migrated
    """
    logger.info("Starting migration of legacy manual_entries data")
    
    if not isinstance(legacy_data, dict):
        raise ValueError("Legacy data must be a dictionary")
    
    # Check if data is already in new format
    if _is_new_format(legacy_data):
        logger.info("Data is already in new format, returning unchanged")
        return legacy_data
    
    # Migrate legacy format
    logger.info("Detected legacy format, starting migration")
    
    migrated_entries = []
    total_fields = 0
    skipped_mappings = 0
    
    try:
        for mapping_id, mapping_fields in legacy_data.items():
            if not isinstance(mapping_fields, dict):
                logger.warning(f"Skipping mapping '{mapping_id}': expected dict, got {type(mapping_fields)}")
                skipped_mappings += 1
                continue
            
            if not mapping_fields:  # Empty mapping
                logger.info(f"Skipping empty mapping '{mapping_id}'")
                skipped_mappings += 1
                continue
            
            # Convert each field in this mapping
            migrated_fields = []
            skipped_fields = 0
            
            for field_name, field_config in mapping_fields.items():
                try:
                    migrated_field = _migrate_field(field_name, field_config)
                    migrated_fields.append(migrated_field)
                    total_fields += 1
                except ValueError as e:
                    logger.warning(f"Skipping field '{field_name}' in mapping '{mapping_id}': {str(e)}")
                    skipped_fields += 1
                    continue
            
            # Only add mapping if it has valid fields
            if migrated_fields:
                migrated_entry = {
                    "id": mapping_id,
                    "fields": migrated_fields
                }
                migrated_entries.append(migrated_entry)
                
                if skipped_fields > 0:
                    logger.info(f"Mapping '{mapping_id}': migrated {len(migrated_fields)} fields, "
                               f"skipped {skipped_fields} fields")
            else:
                logger.warning(f"Mapping '{mapping_id}' contains no valid fields, skipping entirely")
                skipped_mappings += 1
        
        migrated_data = {
            "entries": migrated_entries
        }
        
        logger.info(f"Migration completed: {len(migrated_entries)} mappings, "
                   f"{total_fields} fields migrated, {skipped_mappings} mappings skipped")
        
        return migrated_data
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise ValueError(f"Failed to migrate legacy data: {str(e)}")