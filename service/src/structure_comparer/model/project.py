from pydantic import BaseModel

from .mapping import MappingBase
from .package import Package


class Project(BaseModel):
    name: str
    mappings: list[MappingBase]
    packages: list[Package]


class ProjectInput(BaseModel):
    name: str


class ProjectOverview(BaseModel):
    name: str
    url: str


class ProjectList(BaseModel):
    projects: list[ProjectOverview]
