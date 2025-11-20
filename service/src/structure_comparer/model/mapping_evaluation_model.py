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
    # New status counts matching frontend logic
    total: int
    incompatible: int
    warning: int
    solved: int
    compatible: int
