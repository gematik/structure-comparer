from typing import Dict

from structure_comparer.mapping_evaluation_engine import evaluate_mapping
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
    MappingStatus,
)


class EvalField:
    def __init__(self, name: str, *, is_target_required: bool = False, classification: str = "compatible"):
        self.name = name
        self.is_target_required = is_target_required
        self.classification = classification


class EvalMapping:
    def __init__(self, fields):
        self.fields: Dict[str, EvalField] = {field.name: field for field in fields}


def test_required_target_with_not_use_manual_action_counts_as_solved():
    mapping = EvalMapping([
        EvalField("Practitioner.identifier", is_target_required=True, classification="incompatible"),
    ])
    actions = {
        "Practitioner.identifier": ActionInfo(action=ActionType.NOT_USE, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation: EvaluationResult = result["Practitioner.identifier"]

    assert evaluation.status == EvaluationStatus.ACTION_REQUIRED
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is True
    assert evaluation.reasons
    reason = evaluation.reasons[0]
    assert reason.code == "TARGET_MIN_GT_SOURCE_MIN"
    assert reason.severity == EvaluationSeverity.ERROR
    assert reason.related_action == ActionType.NOT_USE
    assert evaluation.mapping_status == MappingStatus.SOLVED


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
    assert evaluation.mapping_status == MappingStatus.SOLVED


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
    assert evaluation.mapping_status == MappingStatus.COMPATIBLE


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
    assert evaluation.mapping_status == MappingStatus.INCOMPATIBLE


def test_incompatible_field_without_manual_action_is_incompatible():
    mapping = EvalMapping([
        EvalField("Observation.value", is_target_required=True, classification="incompatible"),
    ])
    actions = {
        "Observation.value": ActionInfo(action=None, source=ActionSource.SYSTEM_DEFAULT)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.value"]

    assert evaluation.mapping_status == MappingStatus.INCOMPATIBLE
    assert evaluation.status == EvaluationStatus.ACTION_REQUIRED
    assert evaluation.has_errors is True


def test_incompatible_field_with_manual_action_is_solved():
    mapping = EvalMapping([
        EvalField("Observation.value", is_target_required=False, classification="incompatible"),
    ])
    actions = {
        "Observation.value": ActionInfo(action=ActionType.FIXED, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.value"]

    assert evaluation.mapping_status == MappingStatus.SOLVED
    assert evaluation.status == EvaluationStatus.RESOLVED
    assert evaluation.has_errors is False


def test_warning_field_without_manual_action_is_warning():
    mapping = EvalMapping([
        EvalField("Observation.interpretation", classification="warning"),
    ])
    actions = {
        "Observation.interpretation": ActionInfo(action=None, source=ActionSource.SYSTEM_DEFAULT)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.interpretation"]

    assert evaluation.mapping_status == MappingStatus.WARNING
    assert evaluation.status == EvaluationStatus.ACTION_REQUIRED
    assert evaluation.has_warnings is True
    assert evaluation.has_errors is False


def test_warning_field_with_manual_action_is_solved():
    mapping = EvalMapping([
        EvalField("Observation.interpretation", classification="warning"),
    ])
    actions = {
        "Observation.interpretation": ActionInfo(action=ActionType.EMPTY, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.interpretation"]

    assert evaluation.mapping_status == MappingStatus.SOLVED
    assert evaluation.status == EvaluationStatus.RESOLVED
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is False


def test_manual_action_on_compatible_field_stays_compatible():
    mapping = EvalMapping([
        EvalField("Observation.note", classification="compatible"),
    ])
    actions = {
        "Observation.note": ActionInfo(action=ActionType.FIXED, source=ActionSource.MANUAL)
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.note"]

    assert evaluation.mapping_status == MappingStatus.COMPATIBLE
    assert evaluation.status == EvaluationStatus.OK
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is False


def test_incompatible_field_with_inherited_action_is_solved():
    mapping = EvalMapping([
        EvalField("Medication.extension:isVaccine.url", is_target_required=False, classification="incompatible"),
    ])
    actions = {
        "Medication.extension:isVaccine.url": ActionInfo(
            action=ActionType.COPY_FROM,
            source=ActionSource.INHERITED,
            inherited_from="Medication.extension:isVaccine"
        )
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Medication.extension:isVaccine.url"]

    assert evaluation.mapping_status == MappingStatus.SOLVED
    assert evaluation.status == EvaluationStatus.RESOLVED
    assert evaluation.has_errors is False


def test_warning_field_with_inherited_action_is_solved():
    mapping = EvalMapping([
        EvalField("Observation.interpretation", classification="warning"),
    ])
    actions = {
        "Observation.interpretation": ActionInfo(
            action=ActionType.NOT_USE,
            source=ActionSource.INHERITED,
            inherited_from="Observation"
        )
    }

    result = evaluate_mapping(mapping, actions)
    evaluation = result["Observation.interpretation"]

    assert evaluation.mapping_status == MappingStatus.SOLVED
    assert evaluation.status == EvaluationStatus.RESOLVED
    assert evaluation.has_warnings is False
    assert evaluation.has_errors is False
