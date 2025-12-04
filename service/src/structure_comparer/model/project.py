from pydantic import BaseModel

from .comparison import ComparisonOverview
from .mapping import MappingBase
from .package import Package
from .transformation import TransformationBase
from .target_creation import TargetCreationBase


class Project(BaseModel):
    name: str
    version: str | None = None
    status: str | None = None
    mappings: list[MappingBase]
    comparisons: list[ComparisonOverview]
    transformations: list[TransformationBase] = []
    target_creations: list[TargetCreationBase] = []
    packages: list[Package]


class ProjectInput(BaseModel):
    name: str
    version: str | None = None
    status: str | None = None


class ProjectOverview(BaseModel):
    name: str
    url: str
    version: str | None = None
    status: str | None = None


class ProjectList(BaseModel):
    projects: list[ProjectOverview]
