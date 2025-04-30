from pydantic import BaseModel

from .comparison import ComparisonOverview
from .mapping import MappingBase
from .package import Package


class Project(BaseModel):
    name: str
    mappings: list[MappingBase]
    comparisons: list[ComparisonOverview]
    packages: list[Package]


class ProjectInput(BaseModel):
    name: str


class ProjectOverview(BaseModel):
    name: str
    url: str


class ProjectList(BaseModel):
    projects: list[ProjectOverview]
