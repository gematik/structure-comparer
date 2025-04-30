from pydantic import BaseModel

from .profile import Profile, ProfileField


class ComparisonField(BaseModel):
    name: str
    profiles: dict[str, ProfileField | None]


class ComparisonCreate(BaseModel):
    source_ids: list[str]
    target_id: str


class ComparisonOverview(BaseModel):
    id: str
    name: str
    sources: list[str]
    target: str


class ComparisonDetail(BaseModel):
    id: str
    name: str
    sources: list[Profile]
    target: Profile
    fields: list[ComparisonField]


class ComparisonList(BaseModel):
    comparisons: list[ComparisonOverview]
