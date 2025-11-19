from typing import Dict

from structure_comparer.mapping_evaluation_engine import evaluate_mapping
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
)


class EvalField:
    def __init__(self, name: str, *, is_target_required: bool = False, classification: str = "compatible"):
        self.name = name
        self.is_target_required = is_target_required
        self.classification = classification


class EvalMapping:
    def __init__(self, fields):
        self.fields: Dict[str, EvalField] = {field.name: field for field in fields}


def test_required_target_with_not_use_requires_action():
    mapping = EvalMapping([
        EvalField("Practitioner.identifier", is_target_required=True, classification="incompatible"),
    ])
    actions = {
        "Practitioner.identifier": ActionInfo(action=ActionType.NOT_USE, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation: EvaluationResult = result["Practitioner.identifier"]

    assert evaluation.status == EvaluationStatus.ACTION_REQUIRED
    assert evaluation.has_warnings is True
    assert evaluation.has_errors is False
    assert evaluation.reasons
    reason = evaluation.reasons[0]
    assert reason.code == "TARGET_MIN_GT_SOURCE_MIN"
    assert reason.severity == EvaluationSeverity.WARNING
    assert reason.related_action == ActionType.NOT_USE


def test_required_target_with_extension_is_resolved():
    mapping = EvalMapping([
        EvalField("Practitioner.identifier", is_target_required=True, classification="incompatible"),
    ])
    actions = {
        "Practitioner.identifier": ActionInfo(action=ActionType.EXTENSION, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Practitioner.identifier"]

    assert evaluation.status == EvaluationStatus.RESOLVED
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is False
    assert evaluation.reasons
    reason = evaluation.reasons[0]
    assert reason.severity == EvaluationSeverity.INFO
    assert reason.related_action == ActionType.EXTENSION


def test_compatible_use_is_ok():
    mapping = EvalMapping([
        EvalField("Observation.code", is_target_required=False, classification="compatible"),
    ])
    actions = {
        "Observation.code": ActionInfo(action=ActionType.USE, source=ActionSource.SYSTEM_DEFAULT)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.code"]

    assert evaluation.status == EvaluationStatus.OK
    assert evaluation.reasons == []
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is False


def test_missing_action_results_in_evaluation_failed():
    mapping = EvalMapping([
        EvalField("Observation.value", is_target_required=True, classification="incompatible"),
    ])
    actions = {}

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.value"]

    assert evaluation.status == EvaluationStatus.EVALUATION_FAILED
    assert evaluation.has_errors is True
    assert evaluation.reasons
    assert evaluation.reasons[0].code == "MISSING_ACTION_INFO"
