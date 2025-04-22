from pydantic import BaseModel

from ..action import Action
from .profile import Profile, ProfileField


class MappingField(BaseModel):
    id: str
    name: str
    action: Action
    extra: str | None = None
    profiles: dict[str, ProfileField]
    remark: str
    actions_allowed: list[Action]


class MappingBase(BaseModel):
    id: str
    name: str
    url: str
    version: str
    last_updated: str
    status: str
    sources: list[Profile]
    target: Profile


class MappingDetails(MappingBase):
    fields: list[MappingField]


class MappingFieldsOutput(BaseModel):
    id: str
    fields: list[MappingField]
