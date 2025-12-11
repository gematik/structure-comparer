from pydantic import BaseModel

from ..action import Action
from .mapping_action_models import ActionInfo, EvaluationResult
from .comparison import ComparisonField
from .profile import Profile


class MappingFieldMinimal(BaseModel):
    """Minimal payload accepted when updating a field.

    Convention for action field:
    - None: No action selected yet (user must decide)
    - Action enum value: Specific action chosen (use, not_use, manual, etc.)
    """

    action: Action | None
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None


class MappingFieldBase(MappingFieldMinimal):
    """Manual-entry representation of a field (persisted in YAML/JSON)."""

    name: str
    inherited_from: str | None = None
    auto_generated: bool = False


class MappingField(ComparisonField):
    """Representation returned to clients when requesting mapping details.

    Convention for action field:
    - None: No action has been selected yet. Field requires user decision.
             Typically for warning/incompatible fields without a default action.
    - Action enum value: An action is set (manually, inherited, or system default).
             'manual' specifically means user provided implementation instructions in remark.
    
    Convention for recommendations field:
    - Contains a list of suggested actions that have NOT been applied yet
    - Does NOT influence mapping_status
    - User must explicitly apply one to convert it to active action
    - Empty list [] if no recommendations available
    """

    action: Action | None
    other: str | None = None
    fixed: str | None = None
    actions_allowed: list[Action]
    show_mapping_content: bool | None = None
    action_info: ActionInfo | None = None
    evaluation: EvaluationResult | None = None
    recommendations: list[ActionInfo] = []
    inherited_from: str | None = None
    auto_generated: bool = False


class MappingBase(BaseModel):
    id: str
    name: str
    url: str
    version: str
    last_updated: str
    status: str
    sources: list[Profile]
    target: Profile
    # Status counts calculated by backend
    total: int | None = None
    incompatible: int | None = None
    warning: int | None = None
    solved: int | None = None
    compatible: int | None = None


class MappingCreate(BaseModel):
    source_ids: list[str]
    target_id: str


class ProfileUpdate(BaseModel):
    """Profile metadata for updates."""
    url: str | None = None  # Canonical URL
    version: str | None = None
    webUrl: str | None = None  # Documentation/Simplifier URL
    package: str | None = None


class MappingUpdate(BaseModel):
    """Payload for updating mapping metadata."""
    status: str | None = None
    version: str | None = None
    sources: list[ProfileUpdate] | None = None
    target: ProfileUpdate | None = None


class MappingDetails(MappingBase):
    fields: list[MappingField]


class MappingFieldsOutput(BaseModel):
    id: str
    fields: list[MappingField]


# ============================================================================
# Models for Recursive Field Resolution (Phase 1)
# ============================================================================

class ProfileResolutionInfo(BaseModel):
    """Profile-specific resolution information for a field."""
    can_be_expanded: bool = False  # Has resolvable references?
    resolved_profile_id: str | None = None  # ID of the resolved profile
    type_profiles: list[str] | None = None  # Profile URLs from type[].profile[]
    ref_types: list[str] | None = None  # Target profiles from type[].targetProfile[]


class ResolvedMappingField(BaseModel):
    """Extended mapping field with resolution context.

    This model represents a field that may have been resolved from a
    profile reference (fixedUri, fixedCanonical, type[].profile[], etc.)
    """
    # Basic field information
    name: str  # Full path including resolved prefix
    original_name: str  # Original field name in the source profile
    
    # Profile information per profile key
    source_profiles: dict[str, "ResolvedProfileFieldInfo | None"]
    target_profile: "ResolvedProfileFieldInfo | None"
    
    # Classification and issues
    classification: str  # compat, warn, incompat
    issues: list[str] | None = None
    
    # Action information (same as MappingField)
    action: Action | None = None
    other: str | None = None
    fixed: str | None = None
    actions_allowed: list[Action] = []
    action_info: ActionInfo | None = None
    evaluation: EvaluationResult | None = None
    recommendations: list[ActionInfo] = []
    
    # Resolution metadata
    resolved_from: str | None = None  # Path of the parent field if resolved
    resolution_depth: int = 0  # Depth of resolution (0 = direct field)
    referenced_profile_url: str | None = None  # URL of the referenced profile
    is_expanded: bool = False  # For frontend: Is this branch expanded?
    
    # Profile-specific resolution info
    source_resolution_info: ProfileResolutionInfo | None = None
    target_resolution_info: ProfileResolutionInfo | None = None


class ResolvedProfileFieldInfo(BaseModel):
    """Profile-specific field information with resolution context."""
    min: int
    max: str
    must_support: bool = False
    types: list[str] | None = None
    ref_types: list[str] | None = None
    type_profiles: list[str] | None = None
    cardinality_note: str | None = None
    fixed_value: str | None = None
    fixed_value_type: str | None = None
    
    # Resolution capabilities
    can_be_expanded: bool = False
    resolved_profile_id: str | None = None


class UnresolvedReference(BaseModel):
    """Information about a reference that could not be resolved."""
    field_path: str
    reference_url: str
    reference_type: str  # 'fixedUri', 'fixedCanonical', 'type_profile', 'ref_type'
    profile_context: str  # Which profile this reference is from (source/target)


class ResolutionStats(BaseModel):
    """Statistics about the resolution process."""
    total_fields: int = 0
    resolved_references: int = 0
    unresolved_references: int = 0
    max_depth_reached: int = 0
    profiles_loaded: list[str] = []


class ResolvedMappingFieldsResponse(BaseModel):
    """Response containing recursively resolved mapping fields."""
    id: str  # Mapping ID
    fields: list[ResolvedMappingField]
    unresolved_references: list[UnresolvedReference] = []
    resolution_stats: ResolutionStats
