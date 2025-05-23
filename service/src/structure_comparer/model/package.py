from pydantic import BaseModel


class PackageInfo(BaseModel):
    """
    Package information from the JSON file
    """

    name: str
    version: str
    title: str | None = None
    description: str | None = None
    canonical: str | None = None
    url: str | None = None


class Package(BaseModel):
    display: str | None = None
    id: str
    name: str
    version: str


class PackageInput(BaseModel):
    display: str


class PackageList(BaseModel):
    packages: list[Package]
