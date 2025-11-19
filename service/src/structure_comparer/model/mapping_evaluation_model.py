"""Legacy-compatible Pydantic models used by FastAPI responses."""
from typing import Dict

from pydantic import BaseModel

from ..model.mapping_action_models import EvaluationResult


class MappingEvaluationModel(BaseModel):
    mapping_id: str
    mapping_name: str
    field_evaluations: Dict[str, EvaluationResult]
    summary: Dict[str, int]


class MappingEvaluationSummaryModel(BaseModel):
    mapping_id: str
    mapping_name: str
    total_fields: int
    compatible: int
    warnings: int
    incompatible: int
    action_resolved: int
    action_mitigated: int
    needs_attention: int
    simplified_compatible: int | None = None
    simplified_resolved: int | None = None
    simplified_needs_action: int | None = None
