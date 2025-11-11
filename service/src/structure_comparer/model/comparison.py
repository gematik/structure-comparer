from enum import StrEnum
from pydantic import BaseModel
from .profile import Profile, ProfileField

class ComparisonClassification(StrEnum):
    COMPAT = "compatible"
    WARN = "warning"
    INCOMPAT = "incompatible"
    def __lt__(self, value: str) -> bool:
        other = ComparisonClassification(value)
        return (
            self == ComparisonClassification.COMPAT and other == ComparisonClassification.WARN
        ) or (
            (self in {ComparisonClassification.COMPAT, ComparisonClassification.WARN})
            and other == ComparisonClassification.INCOMPAT
        )

class ComparisonIssue(StrEnum):
    MS = "ms"
    MIN = "min"
    MAX = "max"
    REF = "ref"

class ComparisonField(BaseModel):
    name: str
    profiles: dict[str, ProfileField | None]
    classification: ComparisonClassification
    issues: list[ComparisonIssue] | None
    explanations: list[str] | None = None   # ← NEU

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