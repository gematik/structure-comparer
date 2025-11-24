from structure_comparer.evaluation.status_aggregator import StatusAggregator
from structure_comparer.model.mapping_action_models import (
    EvaluationReason,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
    MappingStatus,
)


def test_build_evaluation_summary_counts_mapping_actions_as_resolved():
    evaluations = {
        "solved": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[],
            has_warnings=False,
            has_errors=True,
            summary_key="mapping.status.action_required",
            mapping_status=MappingStatus.SOLVED,
        ),
        "failed": EvaluationResult(
            status=EvaluationStatus.EVALUATION_FAILED,
            reasons=[
                EvaluationReason(
                    code="error",
                    severity=EvaluationSeverity.ERROR,
                    message_key="mapping.reason.test",
                    details={},
                )
            ],
            has_warnings=False,
            has_errors=True,
            summary_key="mapping.status.evaluation_failed",
            mapping_status=MappingStatus.INCOMPATIBLE,
        ),
    }

    summary = StatusAggregator.build_status_summary(evaluations)

    assert summary["total"] == 2
    assert summary["solved"] == 1
    assert summary["incompatible"] == 1
    assert summary["warning"] == 0
    assert summary["compatible"] == 0
