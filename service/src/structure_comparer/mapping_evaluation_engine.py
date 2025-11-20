"""Experimental mapping evaluation engine (Step 3).

Implemented TDD-first together with `test_mapping_evaluation_engine.py`.
The module intentionally lives next to the legacy evaluator until the
rewrite is complete.
"""
from __future__ import annotations

from typing import Dict, Optional

from .model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationReason,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
    MappingStatus,
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


def derive_mapping_status(field_evaluation: EvaluationResult, action_info: Optional[ActionInfo]) -> MappingStatus:
    """Derive the unified mapping status from evaluation data and optional manual action.

    Rules:
    - Manual or inherited actions (`ActionSource.MANUAL` or `ActionSource.INHERITED`) that resolve
      a conflict (`EvaluationStatus.RESOLVED`) yield `MappingStatus.SOLVED`.
    - Auto-generated actions that resolve incompatible/warning fields also yield `MappingStatus.SOLVED`.
    - Any remaining errors or failed evaluations keep the field `INCOMPATIBLE`.
    - Pure warnings without errors map to `WARNING`.
    - Manual/inherited/auto-generated adjustments on already compatible fields remain `COMPATIBLE`.
    - Everything else defaults to `COMPATIBLE` because no action is required.
    """

    # Check if action was manually set, inherited, or auto-generated with a resolution
    has_explicit_action = (
        action_info is not None
        and (
            action_info.source in (ActionSource.MANUAL, ActionSource.INHERITED)
            or (action_info.source == ActionSource.SYSTEM_DEFAULT and action_info.auto_generated)
        )
    )

    if has_explicit_action:
        if field_evaluation.status == EvaluationStatus.EVALUATION_FAILED:
            return MappingStatus.INCOMPATIBLE

        if (
            field_evaluation.status == EvaluationStatus.ACTION_REQUIRED
            or field_evaluation.status == EvaluationStatus.RESOLVED
            or field_evaluation.has_errors
            or field_evaluation.has_warnings
        ):
            return MappingStatus.SOLVED

        return MappingStatus.COMPATIBLE

    if field_evaluation.status == EvaluationStatus.EVALUATION_FAILED:
        return MappingStatus.INCOMPATIBLE

    if field_evaluation.has_errors or any(
        reason.severity == EvaluationSeverity.ERROR for reason in field_evaluation.reasons
    ):
        return MappingStatus.INCOMPATIBLE

    if field_evaluation.has_warnings or any(
        reason.severity == EvaluationSeverity.WARNING for reason in field_evaluation.reasons
    ):
        return MappingStatus.WARNING

    return MappingStatus.COMPATIBLE


def _evaluate_field(field, action_info: ActionInfo) -> EvaluationResult:
    is_required = bool(getattr(field, "is_target_required", False))
    classification = getattr(field, "classification", "unknown")

    if is_required and action_info.action == ActionType.NOT_USE:
        reason = EvaluationReason(
            code="TARGET_MIN_GT_SOURCE_MIN",
            severity=EvaluationSeverity.ERROR,
            message_key="mapping.reason.target_required.not_use",
            details={"field": field.name},
            related_action=action_info.action,
        )
        return _build_result(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[reason],
            has_warnings=False,
            has_errors=True,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.ACTION_REQUIRED],
            action_info=action_info,
        )

    if is_required and action_info.action == ActionType.EXTENSION:
        reason = EvaluationReason(
            code="TARGET_MIN_GT_SOURCE_MIN",
            severity=EvaluationSeverity.INFO,
            message_key="mapping.reason.target_required.resolved_by_extension",
            details={"field": field.name},
            related_action=action_info.action,
        )
        return _build_result(
            status=EvaluationStatus.RESOLVED,
            reasons=[reason],
            has_warnings=False,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.RESOLVED],
            action_info=action_info,
        )

    if classification == "incompatible":
        # If the field is incompatible but has a valid action selected, it's resolved
        if action_info.action is not None:
            reason = EvaluationReason(
                code="FIELD_INCOMPATIBLE_RESOLVED",
                severity=EvaluationSeverity.INFO,
                message_key="mapping.reason.field.incompatible.resolved",
                details={"field": field.name, "classification": classification},
                related_action=action_info.action,
            )
            return _build_result(
                status=EvaluationStatus.RESOLVED,
                reasons=[reason],
                has_warnings=False,
                has_errors=False,
                summary_key=_SUMMARY_KEYS[EvaluationStatus.RESOLVED],
                action_info=action_info,
            )
        
        # No action selected yet - user decision required
        reason = EvaluationReason(
            code="FIELD_INCOMPATIBLE",
            severity=EvaluationSeverity.ERROR,
            message_key="mapping.reason.field.incompatible",
            details={"field": field.name, "classification": classification},
        )
        return _build_result(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[reason],
            has_warnings=False,
            has_errors=True,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.ACTION_REQUIRED],
            action_info=action_info,
        )

    if classification == "warning":
        # If the field is a warning but has a valid action selected, it's resolved
        if action_info.action is not None:
            reason = EvaluationReason(
                code="FIELD_WARNING_RESOLVED",
                severity=EvaluationSeverity.INFO,
                message_key="mapping.reason.field.warning.resolved",
                details={"field": field.name, "classification": classification},
                related_action=action_info.action,
            )
            return _build_result(
                status=EvaluationStatus.RESOLVED,
                reasons=[reason],
                has_warnings=False,
                has_errors=False,
                summary_key=_SUMMARY_KEYS[EvaluationStatus.RESOLVED],
                action_info=action_info,
            )
        
        # No action selected yet - user decision required
        reason = EvaluationReason(
            code="FIELD_WARNING",
            severity=EvaluationSeverity.WARNING,
            message_key="mapping.reason.field.warning",
            details={"field": field.name, "classification": classification},
        )
        return _build_result(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[reason],
            has_warnings=True,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.ACTION_REQUIRED],
            action_info=action_info,
        )

    if classification == "compatible":
        return _build_result(
            status=EvaluationStatus.OK,
            reasons=[],
            has_warnings=False,
            has_errors=False,
            summary_key=_SUMMARY_KEYS[EvaluationStatus.OK],
            action_info=action_info,
        )

    # Fallback if no specific rule matched.
    return _build_result(
        status=EvaluationStatus.UNKNOWN,
        reasons=[],
        has_warnings=False,
        has_errors=False,
        summary_key=_SUMMARY_KEYS[EvaluationStatus.UNKNOWN],
        action_info=action_info,
    )


def _failure_result(field_name: str, *, code: str, message_key: str) -> EvaluationResult:
    reason = EvaluationReason(
        code=code,
        severity=EvaluationSeverity.ERROR,
        message_key=message_key,
        details={"field": field_name},
    )
    return _build_result(
        status=EvaluationStatus.EVALUATION_FAILED,
        reasons=[reason],
        has_warnings=False,
        has_errors=True,
        summary_key=_SUMMARY_KEYS[EvaluationStatus.EVALUATION_FAILED],
        action_info=None,
    )


def _build_result(
    *,
    status: EvaluationStatus,
    reasons: list[EvaluationReason],
    has_warnings: bool,
    has_errors: bool,
    summary_key: str,
    action_info: Optional[ActionInfo],
) -> EvaluationResult:
    result = EvaluationResult(
        status=status,
        reasons=reasons,
        has_warnings=has_warnings,
        has_errors=has_errors,
        summary_key=summary_key,
        mapping_status=MappingStatus.COMPATIBLE,
    )
    result.mapping_status = derive_mapping_status(result, action_info)
    return result
