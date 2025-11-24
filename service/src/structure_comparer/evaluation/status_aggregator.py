"""Aggregation and summarization of evaluation statuses."""

from typing import Dict
from ..model.mapping_action_models import EvaluationResult, MappingStatus


class StatusAggregator:
    """Aggregates evaluation statuses into summary statistics."""
    
    @staticmethod
    def build_status_summary(
        evaluations: Dict[str, EvaluationResult]
    ) -> Dict[str, int]:
        """
        Calculate status summary matching frontend logic.
        
        This mirrors the logic in SummaryHelper.calculateStatusSummary() and
        StatusHelper.getFieldStatus() from the frontend.
        
        Args:
            evaluations: Evaluation results for all fields
            
        Returns:
            Dictionary with status counts (total, incompatible, warning, solved, compatible)
        """
        summary = {
            "total": len(evaluations),
            "incompatible": 0,
            "warning": 0,
            "solved": 0,
            "compatible": 0,
        }

        for result in evaluations.values():
            status = result.mapping_status
            
            if status == MappingStatus.INCOMPATIBLE:
                summary["incompatible"] += 1
            elif status == MappingStatus.WARNING:
                summary["warning"] += 1
            elif status == MappingStatus.SOLVED:
                summary["solved"] += 1
            elif status == MappingStatus.COMPATIBLE:
                summary["compatible"] += 1

        return summary
    
    @staticmethod
    def calculate_completion_percentage(summary: Dict[str, int]) -> float:
        """
        Calculate the percentage of completed (compatible + solved) fields.
        
        Args:
            summary: Status summary from build_status_summary
            
        Returns:
            Percentage of completed fields (0-100)
        """
        total = summary.get("total", 0)
        if total == 0:
            return 0.0
        
        completed = summary.get("compatible", 0) + summary.get("solved", 0)
        return (completed / total) * 100
