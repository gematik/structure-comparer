"""
Pydantic models for Target Creation API.

Target Creations represent a new entity type alongside Mappings and Transformations.
Unlike Mappings, Target Creations have NO source profile - they only define how
properties of a target profile should be populated.

Key Differences to Mappings:
- No source profiles (only target profile)
- Only 'manual' and 'fixed' actions allowed
- No inheritance (use_recursive)
- No recommendations (no source profile to compare with)
- Status based on: required fields (min > 0) must have an action
- Export: Only manual_entries.yaml (no HTML/StructureMap)

Use Case: Creation of target resources without source data.
"""

from enum import StrEnum

from pydantic import BaseModel

from .mapping_action_models import ActionInfo, EvaluationResult
from .profile import Profile


class TargetCreationAction(StrEnum):
    """Allowed actions for Target Creation fields.
    
    Only 'manual' and 'fixed' are allowed - no source-based actions like
    use, use_recursive, copy_value_from, copy_value_to, etc.
    """
    MANUAL = "manual"
    FIXED = "fixed"


class TargetCreationFieldMinimal(BaseModel):
    """Minimal payload accepted when updating a Target Creation field.
    
    Convention for action field:
    - None: No action selected yet (field is pending)
    - TargetCreationAction value: Specific action chosen (manual or fixed)
    
    Note: No 'other' field since copy_value_from/copy_value_to is not allowed.
    """
    action: TargetCreationAction | None
    fixed: str | None = None  # Required when action=fixed
    remark: str | None = None  # Implementation instructions when action=manual


class TargetCreationFieldBase(TargetCreationFieldMinimal):
    """Manual-entry representation of a Target Creation field (persisted in YAML/JSON)."""
    name: str


class TargetCreationField(BaseModel):
    """Full Target Creation field representation returned to clients.
    
    Convention for action field:
    - None: No action has been selected yet. For required fields (min > 0),
            this means the field needs attention (action_required).
    - TargetCreationAction value: An action is set (manually by user).
    
    Note: No recommendations since there's no source profile to compare with.
    """
    name: str
    types: list[str] | None = None
    min: int
    max: str
    extension: str | None = None
    description: str | None = None
    must_support: bool = False
    
    # Always ['manual', 'fixed'] for Target Creations
    actions_allowed: list[TargetCreationAction]
    
    # Current action state
    action: TargetCreationAction | None = None
    fixed: str | None = None
    remark: str | None = None
    
    # Action info (simplified - no inherited_from, no source-based info)
    action_info: ActionInfo | None = None
    
    # Evaluation result
    evaluation: EvaluationResult | None = None


class TargetCreationBase(BaseModel):
    """Base model for Target Creation list views."""
    id: str
    name: str
    url: str
    version: str
    last_updated: str
    status: str
    target: Profile
    # Status counts calculated by backend
    total: int | None = None
    action_required: int | None = None  # Required fields without action
    resolved: int | None = None  # Fields with action set
    optional_pending: int | None = None  # Optional fields without action


class TargetCreationListItem(TargetCreationBase):
    """List item for Target Creation overview."""
    pass


class TargetCreationCreate(BaseModel):
    """Payload for creating a new Target Creation.
    
    Only target profile is required (no source profiles).
    """
    target_id: str  # Profile ID from packages


class ProfileUpdate(BaseModel):
    """Profile metadata for updates."""
    url: str | None = None
    version: str | None = None
    webUrl: str | None = None
    package: str | None = None


class TargetCreationUpdate(BaseModel):
    """Payload for updating Target Creation metadata."""
    status: str | None = None
    version: str | None = None
    target: ProfileUpdate | None = None


class TargetCreationDetails(TargetCreationBase):
    """Full Target Creation details including fields."""
    fields: list[TargetCreationField]


class TargetCreationFieldsOutput(BaseModel):
    """Output model for target creation field list endpoint."""
    id: str
    fields: list[TargetCreationField]


class TargetCreationEvaluationSummary(BaseModel):
    """Evaluation summary for a Target Creation."""
    target_creation_id: str
    target_creation_name: str
    total: int
    action_required: int  # Required fields (min > 0) without action
    resolved: int  # Fields with action set
    optional_pending: int  # Optional fields (min = 0) without action
