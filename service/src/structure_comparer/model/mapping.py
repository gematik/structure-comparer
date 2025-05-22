from pydantic import BaseModel

from ..action import Action
from .comparison import ComparisonField
from .profile import Profile


class MappingFieldMinimal(BaseModel):
    """Minimal model that is used to update a field"""

    action: Action
    other: str | None = None
    fixed: str | None = None
    remark: str | None = None


class MappingFieldBase(MappingFieldMinimal):
    """Base model that is e.g. written as manual entry"""

    name: str


class MappingField(MappingFieldBase, ComparisonField):
    """Representation for when getting a field"""

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
