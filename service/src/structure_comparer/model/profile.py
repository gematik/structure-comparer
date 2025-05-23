from pydantic import BaseModel


class ProfileMin(BaseModel):
    url: str
    version: str


class Profile(ProfileMin):
    id: str
    key: str
    name: str


class PackageProfile(Profile):
    package: str


class ProfileField(BaseModel):
    min: int
    max: str
    must_support: bool
    ref_types: list[str] | None


class ProfileList(BaseModel):
    profiles: list[PackageProfile]
