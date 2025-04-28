from pydantic import BaseModel


class ComparisonMinimal(BaseModel):
    name: str


class ComparisonBase(ComparisonMinimal):
    source_ids: list[str]
    target_id: str


class ComparisonFull(ComparisonBase):
    pass


class ComparisonList(BaseModel):
    comparisons: list[ComparisonBase]
