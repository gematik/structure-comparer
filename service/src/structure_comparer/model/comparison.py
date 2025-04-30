from pydantic import BaseModel

from .profile import Profile


class ComparisonMinimal(BaseModel):
    name: str


class ComparisonBase(BaseModel):
    source_ids: list[str]
    target_id: str


class ComparisonFull(BaseModel):
    id: str
    name: str
    sources: list[Profile]
    target: Profile


class ComparisonList(BaseModel):
    comparisons: list[ComparisonBase]
