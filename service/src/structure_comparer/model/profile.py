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
    ref_types: list[str] | None = None
    cardinality_note: str | None = None


class ProfileList(BaseModel):
    profiles: list[PackageProfile]


class ProfileDetails(Profile):
    """Profile with full field details."""
    fields: dict[str, ProfileField]
