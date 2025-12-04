"""
Evaluation engine for Target Creation entities.

Target Creation evaluation is simpler than Mapping evaluation:
- No source-target comparison (classification)
- Status based purely on cardinality: required fields (min > 0) need an action
- No inheritance logic
- No recommendations

Status calculation:
- action_required: Required field (min > 0) without action
- resolved: Field with action set (manual or fixed)
- optional_pending: Optional field (min = 0) without action

=== IMPLEMENTATION STATUS ===
Phase 3, Step 3.1: Action Computation für Target Creation ✅
Phase 3, Step 3.2: Evaluation für Target Creation ✅
Created: 2025-12-03
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from ..model.target_creation import (
    TargetCreationAction,
    TargetCreationEvaluationSummary,
    TargetCreationFieldBase,
)
from ..model.manual_entries import ManualEntriesTargetCreation
from ..model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationReason,
    EvaluationResult,
    EvaluationSeverity,
    EvaluationStatus,
    MappingStatus,
)

if TYPE_CHECKING:
    from ..data.target_creation import TargetCreation, TargetCreationField


# Map TargetCreationAction to ActionType for consistent evaluation
_TARGET_ACTION_TO_ACTION_TYPE = {
    TargetCreationAction.MANUAL: ActionType.MANUAL,
    TargetCreationAction.FIXED: ActionType.FIXED,
}


def compute_target_creation_actions(
    target_creation: "TargetCreation",
    manual_entries: ManualEntriesTargetCreation | None = None,
) -> dict[str, ActionInfo]:
    """Compute effective ActionInfo for each field in target_creation.
    
    Simplified compared to Mappings:
    - No inheritance from parent fields
    - No use/use_recursive logic
    - Status based only on: Has the field a manual action?
    
    Args:
        target_creation: The TargetCreation entity
        manual_entries: Manual entries for this target creation
        
    Returns:
        Dictionary mapping field names to ActionInfo objects
    """
    result: dict[str, ActionInfo] = {}
    
    # Build manual entries lookup
    manual_map: dict[str, TargetCreationFieldBase] = {}
    if manual_entries:
        for entry in manual_entries.fields:
            manual_map[entry.name] = entry
    
    for field_name, field in target_creation.fields.items():
        manual_entry = manual_map.get(field_name)
        
        if manual_entry and manual_entry.action is not None:
            # User has set an action
            action_type = _TARGET_ACTION_TO_ACTION_TYPE.get(manual_entry.action)
            result[field_name] = ActionInfo(
                action=action_type,
                source=ActionSource.MANUAL,
                user_remark=manual_entry.remark,
                fixed_value=manual_entry.fixed if manual_entry.action == TargetCreationAction.FIXED else None,
            )
        else:
            # No action set - user must decide
            result[field_name] = ActionInfo(
                action=None,
                source=ActionSource.SYSTEM_DEFAULT,
            )
    
    return result


def evaluate_target_creation_field(
    field: "TargetCreationField",
    action_info: ActionInfo | None = None,
) -> EvaluationResult:
    """Evaluate a single Target Creation field.
    
    Simple evaluation based on cardinality:
    - Field has action (manual/fixed) → 'resolved'
    - Required field (min > 0) without action → 'action_required'
    - Optional field (min = 0) without action → 'ok'
    
    No recommendations, no inheritance.
    
    Args:
        field: The TargetCreationField to evaluate
        action_info: Optional ActionInfo if already computed
        
    Returns:
        EvaluationResult with status and reasons
    """
    is_required = field.min > 0
    has_action = field.action is not None
    
    if has_action:
        # Field has an action set - it's resolved
        return EvaluationResult(
            status=EvaluationStatus.RESOLVED,
            reasons=[
                EvaluationReason(
                    code="TARGET_CREATION_RESOLVED",
                    severity=EvaluationSeverity.INFO,
                    message_key="target_creation.field.resolved",
                    details={"field": field.name, "action": str(field.action)},
                )
            ],
            has_warnings=False,
            has_errors=False,
            summary_key="target_creation.status.resolved",
            mapping_status=MappingStatus.SOLVED,
        )
    
    if is_required:
        # Required field without action - needs attention
        return EvaluationResult(
            status=EvaluationStatus.ACTION_REQUIRED,
            reasons=[
                EvaluationReason(
                    code="TARGET_CREATION_REQUIRED_NO_ACTION",
                    severity=EvaluationSeverity.ERROR,
                    message_key="target_creation.field.required_no_action",
                    details={"field": field.name, "min": field.min},
                )
            ],
            has_warnings=False,
            has_errors=True,
            summary_key="target_creation.status.action_required",
            mapping_status=MappingStatus.INCOMPATIBLE,
        )
    
    # Optional field without action - OK (can be left undefined)
    return EvaluationResult(
        status=EvaluationStatus.OK,
        reasons=[],
        has_warnings=False,
        has_errors=False,
        summary_key="target_creation.status.ok",
        mapping_status=MappingStatus.COMPATIBLE,
    )


def evaluate_target_creation(
    target_creation: "TargetCreation",
    actions: dict[str, ActionInfo] | None = None,
) -> dict[str, EvaluationResult]:
    """Evaluate all fields in a Target Creation.
    
    Args:
        target_creation: The TargetCreation entity
        actions: Optional precomputed action info map
        
    Returns:
        Dictionary mapping field names to EvaluationResult
    """
    results: dict[str, EvaluationResult] = {}
    
    for field_name, field in target_creation.fields.items():
        action_info = actions.get(field_name) if actions else None
        results[field_name] = evaluate_target_creation_field(field, action_info)
    
    return results


class TargetCreationStatusAggregator:
    """Aggregates evaluation statuses for Target Creation fields.
    
    Unlike Mapping status counts (incompatible/warning/solved/compatible),
    Target Creation uses:
    - action_required: Required fields (min > 0) without action
    - resolved: Fields with action set
    - optional_pending: Optional fields (min = 0) without action
    """
    
    @staticmethod
    def build_status_summary(
        fields: OrderedDict[str, "TargetCreationField"]
    ) -> dict[str, int]:
        """Calculate status summary for Target Creation fields.
        
        Args:
            fields: The fields of a TargetCreation entity
            
        Returns:
            Dictionary with status counts:
            - total: Total number of fields
            - action_required: Required fields without action
            - resolved: Fields with action set
            - optional_pending: Optional fields without action
        """
        summary = {
            "total": len(fields),
            "action_required": 0,
            "resolved": 0,
            "optional_pending": 0,
        }
        
        for field in fields.values():
            has_action = field.action is not None
            is_required = field.min > 0
            
            if has_action:
                summary["resolved"] += 1
            elif is_required:
                summary["action_required"] += 1
            else:
                summary["optional_pending"] += 1
        
        return summary
    
    @staticmethod
    def build_evaluation_summary(
        target_creation: "TargetCreation"
    ) -> TargetCreationEvaluationSummary:
        """Build a complete evaluation summary for a Target Creation.
        
        Args:
            target_creation: The TargetCreation entity
            
        Returns:
            TargetCreationEvaluationSummary model
        """
        counts = TargetCreationStatusAggregator.build_status_summary(
            target_creation.fields
        )
        
        return TargetCreationEvaluationSummary(
            target_creation_id=target_creation.id,
            target_creation_name=target_creation.name,
            **counts,
        )
