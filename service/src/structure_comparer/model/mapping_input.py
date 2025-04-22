from pydantic import BaseModel

from ..action import Action


class MappingInput(BaseModel):
    action: Action
    target: str | None = None
    value: str | None = None
