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


class MappingField(ComparisonField):
    """Representation returned to clients when requesting mapping details.

    Convention for action field:
    - None: No action has been selected yet. Field requires user decision.
             Typically for warning/incompatible fields without a default action.
    - Action enum value: An action is set (manually, inherited, or system default).
             'manual' specifically means user provided implementation instructions in remark.
    """

    action: Action | None
    other: str | None = None
    fixed: str | None = None
    actions_allowed: list[Action]
    show_mapping_content: bool | None = None
    action_info: ActionInfo | None = None
    evaluation: EvaluationResult | None = None


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
