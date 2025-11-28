"""High-level analysis of field hierarchies for status and action purposes."""

from typing import Any, Dict, List
from .field_navigator import FieldHierarchyNavigator
from ..model.mapping_action_models import EvaluationResult, MappingStatus


class FieldHierarchyAnalyzer:
    """Analyzes field hierarchies for patterns and aggregated information."""
    
    def __init__(
        self, 
        fields: Dict[str, any], 
        evaluations: Dict[str, EvaluationResult]
    ):
        """
        Args:
            fields: Dictionary mapping field names to field objects
            evaluations: Evaluation results for all fields
        """
        self.navigator = FieldHierarchyNavigator(fields)
        self.evaluations = evaluations
    
    def get_fields_with_status(self, status: MappingStatus) -> List[str]:
        """
        Get all fields with a specific mapping status.
        
        Args:
            status: The mapping status to filter by
            
        Returns:
            List of field names with the specified status
        """
        return [
            field_name 
            for field_name, eval_result in self.evaluations.items()
            if eval_result.mapping_status == status
        ]
    
    def get_incompatible_children(self, parent_field_name: str) -> List[str]:
        """
        Get all direct children that are incompatible.
        
        Args:
            parent_field_name: The parent field name
            
        Returns:
            List of incompatible child field names
        """
        children = self.navigator.get_direct_children(parent_field_name)
        
        return [
            child 
            for child in children
            if self.evaluations.get(child) and 
               self.evaluations[child].mapping_status == MappingStatus.INCOMPATIBLE
        ]
    
    def has_any_incompatible_descendant(self, field_name: str) -> bool:
        """
        Check if a field has any incompatible descendants (recursively).
        
        Args:
            field_name: The field name to check
            
        Returns:
            True if any descendant is incompatible
        """
        descendants = self.navigator.get_all_descendants(field_name)
        
        return any(
            self.evaluations.get(desc) and 
            self.evaluations[desc].mapping_status == MappingStatus.INCOMPATIBLE
            for desc in descendants
        )
    
    def get_hierarchy_status_summary(
        self, 
        field_name: str
    ) -> Dict[MappingStatus, int]:
        """
        Get a summary of statuses for a field and all its descendants.
        
        Args:
            field_name: The field name
            
        Returns:
            Dictionary mapping status to count
        """
        descendants = self.navigator.get_all_descendants(field_name)
        all_fields = [field_name] + descendants
        
        summary: Dict[MappingStatus, int] = {
            MappingStatus.INCOMPATIBLE: 0,
            MappingStatus.WARNING: 0,
            MappingStatus.SOLVED: 0,
            MappingStatus.COMPATIBLE: 0,
        }
        
        for field in all_fields:
            eval_result = self.evaluations.get(field)
            if eval_result:
                status = eval_result.mapping_status
                summary[status] = summary.get(status, 0) + 1
        
        return summary


def all_descendants_compatible(field_name: str, mapping: Dict[str, Any]) -> bool:
    """
    Check if all descendants of a field have classification == "compatible".
    
    Args:
        field_name: The field name to check
        mapping: Dictionary mapping field names to field objects (must have 'classification' attribute)
        
    Returns:
        True if all descendants (children, grandchildren, etc.) are compatible.
        Returns True for fields with no descendants.
    """
    navigator = FieldHierarchyNavigator(mapping)
    descendants = navigator.get_all_descendants(field_name)
    
    # Field without descendants returns True
    if not descendants:
        return True
    
    # Check all descendants
    for desc in descendants:
        field = mapping.get(desc)
        if field is None:
            continue
        
        # Get classification, handle both attribute and dict access
        classification = getattr(field, 'classification', None)
        if classification is None and hasattr(field, '__getitem__'):
            classification = field.get('classification')
        
        # Convert to string for comparison
        if classification is not None and str(classification).lower() != "compatible":
            return False
    
    return True


def all_descendants_compatible_or_solved(
    field_name: str,
    mapping: Dict[str, Any],
    evaluation_map: Dict[str, EvaluationResult],
    action_info_map: Dict[str, Any] = None
) -> bool:
    """
    Check if all descendants are either compatible or solved.

    A descendant is considered OK if either:
    - classification == "compatible", OR
    - classification != "compatible" AND mapping_status == SOLVED in evaluation_map

    Additionally, if action_info_map is provided:
    - At least one descendant must NOT have a manual action
    - If ALL descendants have manual actions, return False (use_recursive not applicable)

    Args:
        field_name: The field name to check
        mapping: Dictionary mapping field names to field objects (must have 'classification' attribute)
        evaluation_map: Dictionary mapping field names to EvaluationResult objects
        action_info_map: Optional dictionary mapping field names to ActionInfo objects.
                         If provided, requires at least one descendant WITHOUT a manual action.

    Returns:
        True if all descendants (children, grandchildren, etc.) are compatible or solved
        AND at least one descendant has no manual action (when action_info_map is provided).
        Returns False for fields where ALL descendants have manual actions.
        Fields without evaluation_map entry are NOT considered solved.
    """
    navigator = FieldHierarchyNavigator(mapping)
    descendants = navigator.get_all_descendants(field_name)

    # Field without descendants:
    # - If action_info_map is provided: return False (use_recursive not applicable)
    # - If no action_info_map: return True (for backward compatibility with recommendations)
    if not descendants:
        return action_info_map is None

    # If action_info_map is provided, check if at least one descendant has no manual action
    if action_info_map is not None:
        has_descendant_without_manual_action = False
        for desc in descendants:
            if not _has_manual_action(desc, action_info_map):
                has_descendant_without_manual_action = True
                break

        # If ALL descendants have manual actions, use_recursive is not applicable
        if not has_descendant_without_manual_action:
            return False

    # Check all descendants (regardless of whether they have manual actions)
    for desc in descendants:
        field = mapping.get(desc)
        if field is None:
            continue

        # Get classification, handle both attribute and dict access
        classification = getattr(field, 'classification', None)
        if classification is None and hasattr(field, '__getitem__'):
            classification = field.get('classification')

        # Convert to string for comparison
        classification_str = str(classification).lower() if classification is not None else ""

        # Check if compatible
        if classification_str == "compatible":
            continue

        # Not compatible - check if solved in evaluation_map
        eval_result = evaluation_map.get(desc)
        if eval_result is None:
            # No evaluation entry means NOT solved
            return False

        # Check mapping_status - handle both Enum and string comparison
        mapping_status = eval_result.mapping_status
        if mapping_status == MappingStatus.SOLVED or str(mapping_status) == "solved":
            continue

        # Neither compatible nor solved
        return False

    return True


def _has_manual_action(field_name: str, action_info_map: Dict[str, Any]) -> bool:
    """
    Check if a field has a manual action annotated.
    
    A field has a manual action if:
    - It exists in action_info_map, AND
    - Its action is not None, AND
    - Its source is MANUAL (not inherited or system default)
    
    Args:
        field_name: The field name to check
        action_info_map: Dictionary mapping field names to ActionInfo objects
        
    Returns:
        True if the field has a manual action, False otherwise
    """
    from ..model.mapping_action_models import ActionSource
    
    action_info = action_info_map.get(field_name)
    if action_info is None:
        return False
    
    # Check if action is set (not None)
    action = getattr(action_info, 'action', None)
    if action is None:
        return False
    
    # Check if source is MANUAL
    source = getattr(action_info, 'source', None)
    if source == ActionSource.MANUAL or str(source) == "manual":
        return True
    
    return False
