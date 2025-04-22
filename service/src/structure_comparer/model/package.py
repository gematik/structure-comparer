from pydantic import BaseModel


class Package(BaseModel):
    display: str | None = None
    id: str
    name: str
    version: str


class PackageInput(BaseModel):
    display: str


class PackageList(BaseModel):
    packages: list[Package]
