import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ..errors import InitializationError

logger = logging.getLogger(__name__)


class PackageConfig(BaseModel):
    name: str
    version: str
    display: str | None = None


class ComparisonProfileConfig(BaseModel):
    id: str | None = None
    url: str | None = None  # Canonical URL for profile lookup
    version: str
    webUrl: str | None = None  # Documentation/Simplifier URL
    package: str | None = None


class ComparisonProfilesConfig(BaseModel):
    sourceprofiles: list[ComparisonProfileConfig]
    targetprofile: ComparisonProfileConfig


class ComparisonConfig(BaseModel):
    id: str
    comparison: ComparisonProfilesConfig = None


class MappingConfig(BaseModel):
    id: str
    version: str
    status: str = "draft"
    mappings: ComparisonProfilesConfig = None
    last_updated: str = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class TransformationConfig(BaseModel):
    """Configuration for a Transformation (meta-level mapping).

    A Transformation bundles multiple Mappings together to describe
    how a complete FHIR Bundle is transformed into another structure.
    """
    id: str
    version: str
    status: str = "draft"
    transformations: ComparisonProfilesConfig = None
    last_updated: str = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class TargetCreationConfig(BaseModel):
    """Configuration for a Target Creation.
    
    Target Creations define how to populate a target profile without source data.
    Unlike Mappings, they have NO source profiles - only a target profile.
    
    Only 'manual' and 'fixed' actions are allowed.
    
    === IMPLEMENTATION STATUS ===
    Phase 2, Step 2.1: TargetCreation Config ✅
    Created: 2025-12-03
    """
    id: str
    version: str
    status: str = "draft"
    targetprofile: ComparisonProfileConfig = None  # Only target, no source profiles
    last_updated: str = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class ProjectConfig(BaseModel):
    name: str | None = None
    version: str | None = None
    status: str | None = None
    manual_entries_file: str = "manual_entries.yaml"
    data_dir: str = "data"
    html_output_dir: str = "docs"
    packages: list[PackageConfig] = []
    comparisons: list[ComparisonConfig] = []
    transformations: list[TransformationConfig] = []  # Meta-level mappings
    target_creations: list[TargetCreationConfig] = []  # NEW: Target-only definitions (Phase 2.1)
    mapping_output_file: str = "mapping.json"
    mappings: list[MappingConfig] = []
    show_remarks: bool = True
    show_warnings: bool = True
    _file_path: Path

    @staticmethod
    def from_json(file: str | Path) -> "ProjectConfig":
        file = Path(file)

        try:
            content = file.read_text(encoding="utf-8")
            config = ProjectConfig.model_validate_json(content)

        except ValidationError as e:
            msg = f"failed to load config from {str(file)}"
            logger.error(msg)
            logger.error(e.errors())
            raise InitializationError(msg)

        else:
            config._file_path = file

            # Fix name if missing
            if config.name is None:
                config.name = file.parent.name

            config.write()
            return config

    def write(self):
        # Note: We use exclude_none but NOT exclude_unset to ensure packages list is written
        # even when it was initially empty and then populated via auto-migration
        # We also explicitly include 'packages' to ensure it's always written
        data = self.model_dump(exclude_none=True)
        # Ensure packages is always present (for package list in config feature)
        if 'packages' not in data:
            data['packages'] = []
        content = json.dumps(data, indent=4, ensure_ascii=False)
        self._file_path.write_text(content, encoding="utf-8")
