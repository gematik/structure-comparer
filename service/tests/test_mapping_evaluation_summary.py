from structure_comparer.serve import _build_evaluation_summary
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

    summary = _build_evaluation_summary(evaluations)

    assert summary["total_fields"] == 2
    assert summary["action_resolved"] == 1
    assert summary["needs_attention"] == 1
    assert summary["incompatible"] == 1
    assert summary["warnings"] == 0
