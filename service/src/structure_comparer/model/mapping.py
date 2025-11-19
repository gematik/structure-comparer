from pydantic import BaseModel

from ..action import Action
from .mapping_action_models import ActionInfo, EvaluationResult
from .comparison import ComparisonField
from .profile import Profile


class MappingFieldMinimal(BaseModel):
    """Minimal payload accepted when updating a field"""

    action: Action
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None


class MappingFieldBase(MappingFieldMinimal):
    """Manual-entry representation of a field (persisted in YAML/JSON)."""

    name: str


class MappingField(ComparisonField):
    """Representation returned to clients when requesting mapping details."""

    action: Action
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


class MappingCreate(BaseModel):
    source_ids: list[str]
    target_id: str


class MappingDetails(MappingBase):
    fields: list[MappingField]


class MappingFieldsOutput(BaseModel):
    id: str
    fields: list[MappingField]
