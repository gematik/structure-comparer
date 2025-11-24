"""Status propagation from children to parents."""

from typing import Dict, List
from ..field_hierarchy.field_navigator import FieldHierarchyNavigator
from ..model.mapping_action_models import (
    EvaluationResult,
    EvaluationReason,
    EvaluationSeverity,
    MappingStatus,
)


class StatusPropagator:
    """Propagates incompatible status from children to parents."""
    
    def __init__(self, fields: Dict[str, any], evaluations: Dict[str, EvaluationResult]):
        """
        Args:
            fields: Mapping of field names to field objects
            evaluations: Current evaluation results for all fields
        """
        self.navigator = FieldHierarchyNavigator(fields)
        self.evaluations = evaluations
        self.propagated_statuses: Dict[str, MappingStatus] = {}
    
    def propagate_incompatible_to_parents(self) -> Dict[str, EvaluationResult]:
        """
        Analyze all fields and mark parents as INCOMPATIBLE if they have
        incompatible children.
        
        Returns:
            Updated evaluation results with propagated statuses
        """
        updated_evaluations = dict(self.evaluations)
        
        # Process in reverse depth order (children first, then parents)
        for field_name in self.navigator.get_fields_by_depth(reverse=True):
            self._check_and_propagate(field_name, updated_evaluations)
        
        return updated_evaluations
    
    def _check_and_propagate(
        self, 
        field_name: str, 
        evaluations: Dict[str, EvaluationResult]
    ) -> None:
        """Check if field has incompatible children and propagate status."""
        
        # Get all direct children
        children = self.navigator.get_direct_children(field_name)
        
        if not children:
            return  # No children, nothing to propagate
        
        # Collect all incompatible children
        incompatible_children = [
            child_name
            for child_name in children
            if evaluations.get(child_name) and 
               evaluations[child_name].mapping_status == MappingStatus.INCOMPATIBLE
        ]
        
        if not incompatible_children:
            return  # All children are compatible
        
        # Parent has incompatible children - update status
        current_eval = evaluations.get(field_name)
        if current_eval:
            # Only propagate if parent is not already incompatible for other reasons
            # This preserves original incompatibility information
            if current_eval.mapping_status != MappingStatus.INCOMPATIBLE:
                # Create updated evaluation with inherited incompatible status
                updated_eval = self._create_inherited_incompatible_evaluation(
                    current_eval, 
                    field_name,
                    incompatible_children
                )
                evaluations[field_name] = updated_eval
    
    def _create_inherited_incompatible_evaluation(
        self,
        original_eval: EvaluationResult,
        parent_name: str,
        incompatible_children: List[str]
    ) -> EvaluationResult:
        """Create new evaluation result with inherited incompatible status."""
        
        # Add a new reason explaining the inherited status
        inherited_reason = EvaluationReason(
            code="INHERITED_INCOMPATIBLE_FROM_CHILDREN",
            severity=EvaluationSeverity.WARNING,
            message_key="mapping.reason.parent.inherited_incompatible",
            details={
                "parent_field": parent_name,
                "incompatible_children_count": len(incompatible_children),
                "incompatible_children": incompatible_children[:5]  # Limit for readability
            }
        )
        
        # Create updated evaluation
        updated_reasons = list(original_eval.reasons) + [inherited_reason]
        
        return EvaluationResult(
            status=original_eval.status,
            reasons=updated_reasons,
            has_warnings=True,  # Inherited incompatibility is a warning
            has_errors=original_eval.has_errors,
            summary_key="mapping.status.inherited_incompatible",
            mapping_status=MappingStatus.INCOMPATIBLE  # Override to INCOMPATIBLE
        )
