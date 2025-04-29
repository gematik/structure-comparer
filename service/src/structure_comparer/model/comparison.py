from pydantic import BaseModel

from .profile import Profile


class ComparisonMinimal(BaseModel):
    name: str


class ComparisonBase(ComparisonMinimal):
    source_ids: list[str]
    target_id: str


class ComparisonFull(ComparisonBase):
    sources: list[Profile]
    target_id: Profile


class ComparisonList(BaseModel):
    comparisons: list[ComparisonBase]
