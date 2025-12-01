"""
Migration script for upgrading config.json files to support transformations.

This script:
1. Detects the config version
2. Migrates old config format to new format with transformations support
3. Preserves all existing mappings and comparisons
4. Optionally creates default transformations from existing mappings

Usage:
    python -m structure_comparer.migration.config_migration <project_dir>
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def detect_config_version(config: dict) -> str:
    """Detect the version of a config file.
    
    Returns:
        '1.0' - Legacy format without transformations
        '2.0' - New format with transformations array
    """
    if 'transformations' in config and isinstance(config.get('transformations'), list):
        return '2.0'
    return '1.0'


def migrate_config_to_v2(config: dict) -> dict:
    """Migrate a v1.0 config to v2.0 format.
    
    The main change is adding an empty 'transformations' array.
    All existing mappings and comparisons are preserved.
    """
    if detect_config_version(config) == '2.0':
        logger.info("Config is already in v2.0 format, no migration needed")
        return config
    
    # Create a copy to avoid modifying the original
    migrated = config.copy()
    
    # Add empty transformations array
    migrated['transformations'] = []
    
    logger.info("Migrated config to v2.0 format (added empty transformations array)")
    return migrated


def create_transformation_from_mappings(
    config: dict,
    name: str,
    source_bundle_url: str,
    source_bundle_version: str,
    target_structure_url: str,
    target_structure_version: str,
    mapping_ids: Optional[list[str]] = None,
) -> dict:
    """Create a new transformation from existing mappings.
    
    This can be used to bootstrap a transformation that groups
    multiple related mappings together.
    
    Args:
        config: The project config
        name: Name for the new transformation
        source_bundle_url: URL of the source bundle profile
        source_bundle_version: Version of the source bundle profile
        target_structure_url: URL of the target structure (e.g., Parameters)
        target_structure_version: Version of the target structure
        mapping_ids: Optional list of mapping IDs to include. If None, all mappings are included.
    
    Returns:
        The new transformation config entry
    """
    # Collect mappings to include
    mappings = config.get('mappings', [])
    if mapping_ids:
        mappings = [m for m in mappings if m['id'] in mapping_ids]
    
    # Create transformation config
    transformation = {
        'id': str(uuid4()),
        'version': '1.0',
        'status': 'draft',
        'last_updated': datetime.now().isoformat(),
        'transformations': {
            'sourceprofiles': [
                {
                    'url': source_bundle_url,
                    'version': source_bundle_version,
                }
            ],
            'targetprofile': {
                'url': target_structure_url,
                'version': target_structure_version,
            }
        }
    }
    
    logger.info(f"Created transformation '{name}' with {len(mappings)} linked mappings")
    return transformation


def migrate_manual_entries_to_v2(manual_entries: dict) -> dict:
    """Migrate manual_entries.yaml from v1 to v2 format.
    
    Changes:
    - 'entries' is renamed to 'mapping_entries'
    - 'transformation_entries' is added as empty array
    
    For backwards compatibility, the old 'entries' is kept but empty.
    """
    migrated = {}
    
    # Check if already in new format
    if 'mapping_entries' in manual_entries or 'transformation_entries' in manual_entries:
        logger.info("manual_entries is already in v2 format")
        return manual_entries
    
    # Migrate entries to mapping_entries
    entries = manual_entries.get('entries', [])
    migrated['mapping_entries'] = entries
    migrated['transformation_entries'] = []
    migrated['entries'] = []  # Keep empty for backwards compat
    
    logger.info(f"Migrated {len(entries)} entries to mapping_entries format")
    return migrated


def migrate_project(project_dir: Path, dry_run: bool = False) -> bool:
    """Migrate a complete project to v2 format.
    
    Args:
        project_dir: Path to the project directory
        dry_run: If True, only show what would be changed without modifying files
    
    Returns:
        True if migration was successful or not needed
    """
    config_file = project_dir / 'config.json'
    
    if not config_file.exists():
        logger.error(f"Config file not found: {config_file}")
        return False
    
    # Load config
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    original_version = detect_config_version(config)
    logger.info(f"Current config version: {original_version}")
    
    if original_version == '2.0':
        logger.info("Project is already in v2 format, no config migration needed")
    else:
        # Migrate config
        migrated_config = migrate_config_to_v2(config)
        
        if dry_run:
            logger.info("[DRY RUN] Would update config.json with transformations array")
        else:
            # Backup original
            backup_file = config_file.with_suffix('.json.bak')
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Created backup: {backup_file}")
            
            # Write migrated config
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(migrated_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Updated config.json to v2 format")
    
    # Check for manual_entries migration
    manual_entries_file = project_dir / config.get('manual_entries_file', 'manual_entries.yaml')
    
    if manual_entries_file.exists():
        import yaml
        
        with open(manual_entries_file, 'r', encoding='utf-8') as f:
            manual_entries = yaml.safe_load(f) or {}
        
        if 'mapping_entries' in manual_entries or 'transformation_entries' in manual_entries:
            logger.info("manual_entries is already in v2 format")
        else:
            migrated_entries = migrate_manual_entries_to_v2(manual_entries)
            
            if dry_run:
                logger.info("[DRY RUN] Would update manual_entries.yaml to v2 format")
            else:
                # Backup original
                backup_file = manual_entries_file.with_suffix('.yaml.bak')
                with open(backup_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(manual_entries, f, default_flow_style=False, allow_unicode=True)
                logger.info(f"Created backup: {backup_file}")
                
                # Write migrated entries
                with open(manual_entries_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(migrated_entries, f, default_flow_style=False, allow_unicode=True)
                logger.info(f"Updated manual_entries.yaml to v2 format")
    
    logger.info("Migration completed successfully")
    return True


def main():
    """Main entry point for the migration script."""
    if len(sys.argv) < 2:
        print("Usage: python -m structure_comparer.migration.config_migration <project_dir> [--dry-run]")
        print("\nOptions:")
        print("  --dry-run    Show what would be changed without modifying files")
        sys.exit(1)
    
    project_dir = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv
    
    if not project_dir.exists():
        logger.error(f"Project directory not found: {project_dir}")
        sys.exit(1)
    
    if dry_run:
        logger.info("Running in DRY RUN mode - no files will be modified")
    
    success = migrate_project(project_dir, dry_run=dry_run)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
