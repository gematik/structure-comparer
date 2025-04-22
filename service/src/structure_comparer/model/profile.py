from pydantic import BaseModel


class Profile(BaseModel):
    id: str
    profile_key: str
    name: str
    version: str


class PackageProfile(Profile):
    package: str


class ProfileField(BaseModel):
    min: int
    max: str
    must_support: bool


class ProfileList(BaseModel):
    profiles: list[PackageProfile]
