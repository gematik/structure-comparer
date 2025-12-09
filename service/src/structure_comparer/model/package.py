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
    dependencies: dict[str, str] | None = None  # Package dependencies: {"name": "version"}


class Package(BaseModel):
    display: str | None = None
    id: str
    name: str
    version: str


class PackageInput(BaseModel):
    display: str


class PackageList(BaseModel):
    packages: list[Package]


class PackageDownloadRequest(BaseModel):
    """Request to download a package from a FHIR registry."""
    package_name: str
    version: str


class PackageDownloadResult(BaseModel):
    """Result of a package download operation."""
    success: bool
    package_key: str  # name#version
    message: str
    registry_url: str | None = None  # Which registry was used
    package: Package | None = None  # The created package if successful


class BatchDownloadRequest(BaseModel):
    """Request to download multiple packages from FHIR registries."""
    packages: list[PackageDownloadRequest]


class BatchDownloadResult(BaseModel):
    """Result of a batch package download operation."""
    total_requested: int
    successful: int
    failed: int
    results: list[PackageDownloadResult]

