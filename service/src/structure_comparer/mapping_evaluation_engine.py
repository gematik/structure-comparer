"""Experimental mapping evaluation engine (Step 3).

Implemented TDD-first together with `test_mapping_evaluation_engine.py`.
The module intentionally lives next to the legacy evaluator until the
rewrite is complete.
"""
from __future__ import annotations

from typing import Dict

from .model.mapping_action_models import (
    ActionInfo,
    ActionType,
    EvaluationReason,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
)

_SUMMARY_KEYS = {
    EvaluationStatus.OK: "mapping.status.ok",
    EvaluationStatus.ACTION_REQUIRED: "mapping.status.action_required",
    EvaluationStatus.RESOLVED: "mapping.status.resolved",
    EvaluationStatus.EVALUATION_FAILED: "mapping.status.evaluation_failed",
    EvaluationStatus.UNKNOWN: "mapping.status.unknown",
    EvaluationStatus.INCOMPATIBLE: "mapping.status.incompatible",
}


def evaluate_mapping(mapping, actions: Dict[str, ActionInfo]) -> Dict[str, EvaluationResult]:
    """Evaluate each field in *mapping* using precomputed *actions*."""

    fields = getattr(mapping, "fields", {}) or {}
    results: Dict[str, EvaluationResult] = {}

    for field_name, field in fields.items():
        try:
            action_info = actions.get(field_name)
            if action_info is None:
                results[field_name] = _failure_result(
                    field_name,
                    code="MISSING_ACTION_INFO",
                    message_key="mapping.reason.missing_action",
                )
                continue

            results[field_name] = _evaluate_field(field, action_info)
        except Exception:
            results[field_name] = _failure_result(
                field_name,
                code="EVALUATION_EXCEPTION",
                message_key="mapping.reason.evaluation_exception",
            )

    return results


def _evaluate_field(field, action_info: ActionInfo) -> EvaluationResult:
    is_required = bool(getattr(field, "is_target_required", False))
    classification = getattr(field, "classification", "unknown")

    if is_required and action_info.action == ActionType.NOT_USE:
        reason = EvaluationReason(
            code="TARGET_MIN_GT_SOURCE_MIN",
            severity=EvaluationSeverity.WARNING,
            message_key="mapping.reason.target_required.not_use",
            details={"field": field.name},
            related_action=action_info.action,
        )
        return EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[reason],
            has_warnings=True,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.ACTION_REQUIRED],
        )

    if is_required and action_info.action == ActionType.EXTENSION:
        reason = EvaluationReason(
            code="TARGET_MIN_GT_SOURCE_MIN",
            severity=EvaluationSeverity.INFO,
            message_key="mapping.reason.target_required.resolved_by_extension",
            details={"field": field.name},
            related_action=action_info.action,
        )
        return EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            reasons=[reason],
            has_warnings=False,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.RESOLVED],
        )

    if classification in {"compatible", "warning"} and action_info.action == ActionType.USE:
        return EvaluationResult(
            status=EvaluationStatus.OK,
            reasons=[],
            has_warnings=False,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.OK],
        )

    # Fallback if no specific rule matched.
    return EvaluationResult(
        status=EvaluationStatus.UNKNOWN,
        reasons=[],
        has_warnings=False,
        has_errors=False,
        summary_key=_SUMMARY_KEYS[EvaluationStatus.UNKNOWN],
    )


def _failure_result(field_name: str, *, code: str, message_key: str) -> EvaluationResult:
    reason = EvaluationReason(
        code=code,
        severity=EvaluationSeverity.ERROR,
        message_key=message_key,
        details={"field": field_name},
    )
    return EvaluationResult(
        status=EvaluationStatus.EVALUATION_FAILED,
        reasons=[reason],
        has_warnings=False,
        has_errors=True,
        summary_key=_SUMMARY_KEYS[EvaluationStatus.EVALUATION_FAILED],
    )
