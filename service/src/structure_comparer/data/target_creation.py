"""
Data class for Target Creation entities.

Target Creations are a third entity type alongside Mappings and Transformations.
Unlike Mappings, Target Creations have NO source profile - they only define how
properties of a target profile should be populated.

Key Differences to Mappings:
- No source profiles (only target profile)
- Only 'manual' and 'fixed' actions allowed
- No inheritance (use_recursive)
- No recommendations (no source profile to compare with)
- Status based on: required fields (min > 0) must have an action
- Export: Only manual_entries.yaml (no HTML/StructureMap)

=== IMPLEMENTATION STATUS ===
Phase 2, Step 2.1: TargetCreation Data Class erstellen ✅
Created: 2025-12-03
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from ..model.target_creation import (
    TargetCreationAction,
    TargetCreationBase as TargetCreationBaseModel,
    TargetCreationDetails as TargetCreationDetailsModel,
    TargetCreationField as TargetCreationFieldModel,
    TargetCreationFieldBase,
)
from ..model.profile import Profile as ProfileModel
from .config import TargetCreationConfig
from .profile import Profile

if TYPE_CHECKING:
    from .project import Project

logger = logging.getLogger(__name__)


class TargetCreationField:
    """A field within a Target Creation.
    
    Target Creation fields are simpler than Mapping fields:
    - No source profile comparison
    - Only 'manual' and 'fixed' actions allowed
    - actions_allowed is always ['manual', 'fixed']
    - No inheritance logic
    - Status based purely on cardinality (min > 0 requires action)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.types: list[str] | None = None
        self.min: int = 0
        self.max: str = "*"
        self.extension: str | None = None
        self.description: str | None = None
        self.must_support: bool = False
        
        # Always ['manual', 'fixed'] for Target Creations
        self.actions_allowed: list[TargetCreationAction] = [
            TargetCreationAction.MANUAL,
            TargetCreationAction.FIXED,
        ]
        
        # Current action state (populated from manual entries)
        self.action: TargetCreationAction | None = None
        self.fixed: str | None = None
        self.remark: str | None = None
        
        # Action info and evaluation (populated by evaluation engine)
        self.action_info = None
        self.evaluation = None

    @property
    def is_required(self) -> bool:
        """Check if this field is required (min > 0)."""
        return self.min > 0

    def apply_manual_entry(self, entry: TargetCreationFieldBase) -> None:
        """Apply a manual entry to this field."""
        self.action = entry.action
        self.fixed = entry.fixed
        self.remark = entry.remark

    def to_model(self) -> TargetCreationFieldModel:
        """Convert to Pydantic model for API response."""
        return TargetCreationFieldModel(
            name=self.name,
            types=self.types,
            min=self.min,
            max=self.max,
            extension=self.extension,
            description=self.description,
            must_support=self.must_support,
            actions_allowed=self.actions_allowed,
            action=self.action,
            fixed=self.fixed,
            remark=self.remark,
            action_info=self.action_info,
            evaluation=self.evaluation,
        )


class TargetCreation:
    """A Target Creation entity - defines how to populate a target profile without source data.
    
    Unlike Mapping (which compares source and target profiles), TargetCreation:
    - Has only a target profile
    - Does not use inheritance or classification logic
    - Only supports 'manual' and 'fixed' actions
    - Status is based purely on whether required fields have actions
    """

    def __init__(self, config: TargetCreationConfig, project: "Project") -> None:
        self._config = config
        self._project = project
        self.target: Profile | None = None
        self._target_config = config.targetprofile
        self.fields: OrderedDict[str, TargetCreationField] = OrderedDict()

    def init_ext(self) -> "TargetCreation":
        """Initialize the target creation with profile and fields."""
        self._load_target()
        self._gen_fields()
        self._apply_manual_entries()
        return self

    @property
    def id(self) -> str:
        return self._config.id

    @property
    def name(self) -> str:
        """Generate a name from the target profile."""
        if self.target is None:
            return ""
        return f"{self.target.name}|{self.target.version}"

    @property
    def version(self) -> str:
        return self._config.version

    @property
    def last_updated(self) -> str:
        return self._config.last_updated

    @property
    def status(self) -> str:
        return self._config.status

    @property
    def url(self) -> str:
        return f"/project/{self._project.key}/target-creation/{self.id}"

    def _load_target(self) -> None:
        """Load the target profile from project packages."""
        cfg = self._target_config
        if cfg and cfg.url:
            self.target = self._project.get_profile(cfg.id, cfg.url, cfg.version)
            if not self.target:
                logger.error(
                    "Target profile %s url=%s version=%s not found",
                    cfg.id, cfg.url, cfg.version
                )

    def _gen_fields(self) -> None:
        """Generate fields from the target profile.
        
        For Target Creations, we only load fields from the target profile.
        There is no source profile comparison.
        """
        if self.target is None:
            logger.warning("Cannot generate fields: target profile not loaded")
            return

        for field in self.target.fields.values():
            field_name = field.path_full
            
            tc_field = TargetCreationField(field_name)
            tc_field.types = field.types if hasattr(field, 'types') else None
            tc_field.min = field.min if hasattr(field, 'min') else 0
            tc_field.max = str(field.max) if hasattr(field, 'max') else "*"
            tc_field.extension = field.extension if hasattr(field, 'extension') else None
            tc_field.description = field.short if hasattr(field, 'short') else None
            tc_field.must_support = getattr(field, 'must_support', False)
            
            self.fields[field_name] = tc_field

    def _apply_manual_entries(self) -> None:
        """Apply manual entries from the project."""
        manual_entries = self._project.manual_entries
        tc_entries = manual_entries.get_target_creation(self.id)
        
        if tc_entries is None:
            return
            
        for field in tc_entries.fields:
            if field.name in self.fields:
                self.fields[field.name].apply_manual_entry(field)

    def get_profile_metadata(self) -> dict:
        """Get metadata (webUrl, package) for the target profile from its config."""
        if self._target_config:
            return {
                "webUrl": self._target_config.webUrl,
                "package": self._target_config.package
            }
        return {"webUrl": None, "package": None}

    def to_base_model(self) -> TargetCreationBaseModel:
        """Convert to base model for list views."""
        if self.target is None:
            raise ValueError("Target profile not loaded")

        # Create target model with metadata
        metadata = self.get_profile_metadata()
        target = ProfileModel(
            id=self.target.id,
            url=self.target.url,
            key=self.target.key,
            name=self.target.name,
            version=self.target.version,
            webUrl=metadata.get("webUrl"),
            package=metadata.get("package"),
        )

        # Calculate status counts using TargetCreation-specific aggregator
        from ..evaluation.target_creation_evaluation import TargetCreationStatusAggregator
        status_counts = TargetCreationStatusAggregator.build_status_summary(self.fields)

        return TargetCreationBaseModel(
            id=self.id,
            name=self.name,
            url=self.url,
            version=self.version,
            last_updated=self.last_updated,
            status=self.status,
            target=target,
            **status_counts,
        )

    def to_details_model(self) -> TargetCreationDetailsModel:
        """Convert to details model with all fields."""
        if self.target is None:
            raise ValueError("Target profile not loaded")

        # Create target model with metadata
        metadata = self.get_profile_metadata()
        target = ProfileModel(
            id=self.target.id,
            url=self.target.url,
            key=self.target.key,
            name=self.target.name,
            version=self.target.version,
            webUrl=metadata.get("webUrl"),
            package=metadata.get("package"),
        )

        # Compute actions and evaluations for all fields
        from ..evaluation.target_creation_evaluation import (
            compute_target_creation_actions,
            evaluate_target_creation,
            TargetCreationStatusAggregator
        )
        
        # Get manual entries for this target creation
        manual_entry = self._project.manual_entries.get_target_creation(self.id)
        
        # Compute action info
        action_map = compute_target_creation_actions(self, manual_entry)
        
        # Evaluate fields
        evaluation_map = evaluate_target_creation(self, action_map)
        
        # Update fields with action_info and evaluation
        for field in self.fields.values():
            field.action_info = action_map.get(field.name)
            field.evaluation = evaluation_map.get(field.name)
        
        # Convert fields to models (now with action_info and evaluation)
        field_models = [f.to_model() for f in self.fields.values()]

        # Calculate status counts based on evaluations
        status_counts = TargetCreationStatusAggregator.build_status_summary(self.fields)

        return TargetCreationDetailsModel(
            id=self.id,
            name=self.name,
            url=self.url,
            version=self.version,
            last_updated=self.last_updated,
            status=self.status,
            target=target,
            fields=field_models,
            **status_counts,
        )
