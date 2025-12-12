from enum import Enum
from pydantic import BaseModel


class PackageStatus(str, Enum):
    """Status of a package relative to config and filesystem."""
    AVAILABLE = "available"   # In config AND downloaded in data folder
    MISSING = "missing"       # In config but NOT downloaded
    ORPHANED = "orphaned"     # Downloaded but NOT in config


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
    status: PackageStatus | None = None
    description: str | None = None
    canonical: str | None = None


class PackageWithStatus(BaseModel):
    """Extended Package model with download/config status."""
    display: str | None = None
    id: str
    name: str
    version: str
    status: PackageStatus
    # Optional: Additional metadata
    description: str | None = None
    canonical: str | None = None
    source_registry: str | None = None


class PackageInput(BaseModel):
    display: str


class PackageAddRequest(BaseModel):
    """Request to add a package to config (without download)."""
    name: str
    version: str
    display: str | None = None


class PackageAddResult(BaseModel):
    """Result of adding a package to config."""
    success: bool
    package: PackageWithStatus | None = None
    message: str | None = None


class PackageList(BaseModel):
    packages: list[Package]


class PackageListWithStatus(BaseModel):
    """Package list with status information and statistics."""
    packages: list[PackageWithStatus]
    total: int
    available: int
    missing: int
    orphaned: int


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


class OrphanedCleanupResult(BaseModel):
    """Result of cleaning up orphaned packages."""
    success: bool
    deleted: list[str]
    count: int


class OrphanedAdoptResult(BaseModel):
    """Result of adopting orphaned packages into config."""
    success: bool
    adopted: list[str]
    count: int

