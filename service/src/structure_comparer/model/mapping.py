from pydantic import BaseModel

from ..action import Action
from .profile import Profile, ProfileField


class MappingFieldBase(BaseModel):
    action: Action
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None


class MappingField(MappingFieldBase):
    name: str
    profiles: dict[str, ProfileField]
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
