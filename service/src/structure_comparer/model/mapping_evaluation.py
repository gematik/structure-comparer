"""
Pydantic models for enhanced mapping evaluation
"""
from typing import Dict, List, Optional
from pydantic import BaseModel

from ..action import Action
from ..model.comparison import ComparisonClassification, ComparisonIssue


class EvaluationIssueModel(BaseModel):
    """Model for evaluation issue"""
    issue_type: ComparisonIssue
    severity: str  # EvaluationResult as string
    message: str
    resolved_by_action: Optional[Action] = None
    requires_attention: bool = True


class FieldEvaluationModel(BaseModel):
    """Model for field evaluation result"""
    field_name: str
    original_classification: ComparisonClassification
    enhanced_classification: str  # EvaluationResult as string
    action: Action
    issues: List[EvaluationIssueModel]
    warnings: List[str]
    recommendations: List[str]
    processing_status: Optional[str] = None  # "completed" | "resolved" | "needs_action"


class MappingEvaluationModel(BaseModel):
    """Model for complete mapping evaluation"""
    mapping_id: str
    mapping_name: str
    field_evaluations: Dict[str, FieldEvaluationModel]
    summary: Dict[str, int]


class MappingEvaluationSummaryModel(BaseModel):
    """Model for mapping evaluation summary"""
    mapping_id: str
    mapping_name: str
    total_fields: int
    compatible: int
    warnings: int
    incompatible: int
    action_resolved: int
    action_mitigated: int
    needs_attention: int
