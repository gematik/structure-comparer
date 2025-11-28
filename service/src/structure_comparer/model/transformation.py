"""
Pydantic models for Transformation API.

Transformations represent a higher-level mapping concept that bundles multiple
profile-to-profile mappings together. A Transformation describes how a complete
FHIR Bundle (e.g., KBV_PR_ERP_Bundle) is transformed into another format
(e.g., ePA Parameters).

Hierarchy:
- Transformation: Bundle → Parameters (meta-level)
  - TransformationField: References child Mappings via 'map' field
    - Mapping: Profile → Profile (detail-level)
"""

from pydantic import BaseModel

from ..action import Action
from .mapping_action_models import ActionInfo, EvaluationResult
from .profile import Profile


class TransformationFieldMinimal(BaseModel):
    """Minimal payload accepted when updating a transformation field.
    
    Fields have action='transform' and reference a child mapping via 'map'.
    """
    action: Action | None
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None
    map: str | None = None  # Reference to a Mapping ID


class TransformationFieldBase(TransformationFieldMinimal):
    """Manual-entry representation of a transformation field (persisted in YAML/JSON)."""
    name: str


class TransformationField(BaseModel):
    """Full transformation field representation returned to clients.
    
    A TransformationField describes how a specific element from the source Bundle
    maps to the target structure, potentially using a referenced Mapping.
    """
    name: str
    path: str
    action: Action | None
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None
    map: str | None = None  # Reference to Mapping ID
    map_name: str | None = None  # Resolved Mapping name for display
    actions_allowed: list[Action] = []
    action_info: ActionInfo | None = None
    evaluation: EvaluationResult | None = None
    recommendations: list[ActionInfo] = []
    
    # Source and Target field info
    source_min: int | None = None
    source_max: str | None = None
    target_min: int | None = None
    target_max: str | None = None


class TransformationBase(BaseModel):
    """Base model for Transformation list views."""
    id: str
    name: str
    url: str
    version: str
    last_updated: str
    status: str
    sources: list[Profile]
    target: Profile
    # Linked mappings count
    linked_mappings_count: int = 0
    # Status counts
    total: int | None = None
    incompatible: int | None = None
    warning: int | None = None
    solved: int | None = None
    compatible: int | None = None


class TransformationCreate(BaseModel):
    """Payload for creating a new Transformation."""
    source_ids: list[str]  # Profile IDs from packages
    target_id: str  # Profile ID from packages


class ProfileUpdate(BaseModel):
    """Profile metadata for updates."""
    url: str | None = None
    version: str | None = None
    webUrl: str | None = None
    package: str | None = None


class TransformationUpdate(BaseModel):
    """Payload for updating Transformation metadata."""
    status: str | None = None
    version: str | None = None
    sources: list[ProfileUpdate] | None = None
    target: ProfileUpdate | None = None


class TransformationDetails(TransformationBase):
    """Full Transformation details including fields."""
    fields: list[TransformationField]
    linked_mappings: list["MappingReference"] = []


class MappingReference(BaseModel):
    """Lightweight reference to a linked Mapping."""
    id: str
    name: str
    url: str
    version: str
    status: str


class TransformationFieldsOutput(BaseModel):
    """Output model for transformation field list endpoint."""
    id: str
    fields: list[TransformationField]


class TransformationMappingLink(BaseModel):
    """Model for linking/unlinking a Mapping to a Transformation field."""
    mapping_id: str | None = None  # None to unlink
    other: str | None = None  # Target profile field path
    action: Action | None = None  # Optional action to set when linking


# Avoid circular import
TransformationDetails.model_rebuild()
