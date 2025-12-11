"""Tests for StatusPropagator with manual actions."""

from structure_comparer.evaluation.status_propagator import StatusPropagator
from structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
    MappingStatus,
)


class StubField:
    def __init__(self, name: str):
        self.name = name


def test_parent_with_manual_action_not_marked_as_inherited_incompatible():
    """Test that parent fields with manual actions are not marked as inherited incompatible."""
    
    # Setup fields
    fields = {
        "Organization.address:Strassenanschrift.line.extension": StubField(
            "Organization.address:Strassenanschrift.line.extension"
        ),
        "Organization.address:Strassenanschrift.line.extension:Hausnummer": StubField(
            "Organization.address:Strassenanschrift.line.extension:Hausnummer"
        ),
    }
    
    # Parent has SOLVED status (manual extension action)
    # Child is INCOMPATIBLE
    evaluations = {
        "Organization.address:Strassenanschrift.line.extension": EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            reasons=[],
            has_warnings=False,
            has_errors=False,
            summary_key="mapping.status.resolved",
            mapping_status=MappingStatus.SOLVED
        ),
        "Organization.address:Strassenanschrift.line.extension:Hausnummer": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[],
            has_warnings=False,
            has_errors=True,
            summary_key="mapping.status.incompatible",
            mapping_status=MappingStatus.INCOMPATIBLE
        ),
    }
    
    # Parent has manual COPY_NODE_TO action
    actions = {
        "Organization.address:Strassenanschrift.line.extension": ActionInfo(
            action=ActionType.COPY_NODE_TO,
            source=ActionSource.MANUAL,
            other_value="Organization.address.line"
        ),
    }
    
    # Run propagator
    propagator = StatusPropagator(fields, evaluations, actions)
    updated_evaluations = propagator.propagate_incompatible_to_parents()
    
    # Parent should still be SOLVED (not changed to INCOMPATIBLE)
    parent_eval = updated_evaluations["Organization.address:Strassenanschrift.line.extension"]
    assert parent_eval.mapping_status == MappingStatus.SOLVED
    
    # Should not have inherited_incompatible reason
    reason_codes = [r.code for r in parent_eval.reasons]
    assert "INHERITED_INCOMPATIBLE_FROM_CHILDREN" not in reason_codes


def test_parent_without_manual_action_marked_as_inherited_incompatible():
    """Test that parent fields without manual actions are marked as inherited incompatible."""
    
    # Setup fields
    fields = {
        "Organization.address": StubField("Organization.address"),
        "Organization.address.line": StubField("Organization.address.line"),
    }
    
    # Parent is COMPATIBLE, child is INCOMPATIBLE
    evaluations = {
        "Organization.address": EvaluationResult(
            status=EvaluationStatus.OK,
            reasons=[],
            has_warnings=False,
            has_errors=False,
            summary_key="mapping.status.ok",
            mapping_status=MappingStatus.COMPATIBLE
        ),
        "Organization.address.line": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[],
            has_warnings=False,
            has_errors=True,
            summary_key="mapping.status.incompatible",
            mapping_status=MappingStatus.INCOMPATIBLE
        ),
    }
    
    # No manual actions
    actions = {}
    
    # Run propagator
    propagator = StatusPropagator(fields, evaluations, actions)
    updated_evaluations = propagator.propagate_incompatible_to_parents()
    
    # Parent should now be INCOMPATIBLE (inherited from child)
    parent_eval = updated_evaluations["Organization.address"]
    assert parent_eval.mapping_status == MappingStatus.INCOMPATIBLE
    
    # Should have inherited_incompatible reason
    reason_codes = [r.code for r in parent_eval.reasons]
    assert "INHERITED_INCOMPATIBLE_FROM_CHILDREN" in reason_codes


def test_parent_with_inherited_action_still_marked_as_inherited_incompatible():
    """Test that parent fields with inherited (not manual) actions can still be marked as inherited incompatible."""
    
    # Setup fields
    fields = {
        "Organization.address": StubField("Organization.address"),
        "Organization.address.line": StubField("Organization.address.line"),
    }
    
    # Parent is COMPATIBLE, child is INCOMPATIBLE
    evaluations = {
        "Organization.address": EvaluationResult(
            status=EvaluationStatus.OK,
            reasons=[],
            has_warnings=False,
            has_errors=False,
            summary_key="mapping.status.ok",
            mapping_status=MappingStatus.COMPATIBLE
        ),
        "Organization.address.line": EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[],
            has_warnings=False,
            has_errors=True,
            summary_key="mapping.status.incompatible",
            mapping_status=MappingStatus.INCOMPATIBLE
        ),
    }
    
    # Parent has INHERITED action (not manual)
    actions = {
        "Organization.address": ActionInfo(
            action=ActionType.USE_RECURSIVE,
            source=ActionSource.INHERITED,
            inherited_from="Organization"
        ),
    }
    
    # Run propagator
    propagator = StatusPropagator(fields, evaluations, actions)
    updated_evaluations = propagator.propagate_incompatible_to_parents()
    
    # Parent should be marked as INCOMPATIBLE (inherited actions don't prevent propagation)
    parent_eval = updated_evaluations["Organization.address"]
    assert parent_eval.mapping_status == MappingStatus.INCOMPATIBLE
    
    # Should have inherited_incompatible reason
    reason_codes = [r.code for r in parent_eval.reasons]
    assert "INHERITED_INCOMPATIBLE_FROM_CHILDREN" in reason_codes
