"""
Migration utilities for the Structure Comparer.

This module contains scripts for migrating projects between different
data format versions.
"""

from .config_migration import (
    detect_config_version,
    migrate_config_to_v2,
    migrate_manual_entries_to_v2,
    migrate_project,
)

__all__ = [
    'detect_config_version',
    'migrate_config_to_v2',
    'migrate_manual_entries_to_v2',
    'migrate_project',
]
