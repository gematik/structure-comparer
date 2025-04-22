from pydantic import BaseModel

from .mapping import MappingBase


class GetMappingsOutput(BaseModel):
    mappings: list[MappingBase]
