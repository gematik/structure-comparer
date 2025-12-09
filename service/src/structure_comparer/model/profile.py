from typing import Any

from pydantic import BaseModel


class ProfileMin(BaseModel):
    url: str
    version: str


class Profile(ProfileMin):
    id: str
    key: str
    name: str
    webUrl: str | None = None
    package: str | None = None


class PackageProfile(Profile):
    package: str


class ProfileField(BaseModel):
    min: int
    max: str
    must_support: bool
    types: list[str] | None = None
    type_profiles: list[str] | None = None  # Profile URLs from type[].profile[]
    ref_types: list[str] | None = None
    cardinality_note: str | None = None
    fixed_value: Any | None = None
    fixed_value_type: str | None = None


class ResolvedProfileField(ProfileField):
    """Extended profile field with resolved reference information."""
    full_path: str  # Full path including parent context (e.g., "Bundle.entry:Medication.resource.code")
    source_profile_id: str  # The profile this field was loaded from
    source_profile_key: str | None = None  # Profile key (url|version)
    unresolved_reference: str | None = None  # URL if a fixedUri/fixedCanonical could not be resolved
    is_resource_field: bool = False  # True if this field is a .resource field (entry point)


class ProfileList(BaseModel):
    profiles: list[PackageProfile]


class ProfileDetails(Profile):
    """Profile with full field details."""
    fields: dict[str, ProfileField]


class ResolvedProfileFieldsResponse(BaseModel):
    """Response containing recursively resolved profile fields."""
    resource_fields: list[ResolvedProfileField]  # Fields that are resource entry points
    value_fields: list[ResolvedProfileField]  # Fields that are value types (primitives, etc.)
    unresolved_references: list[str] = []  # List of URLs that could not be resolved
