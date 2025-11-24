"""High-level analysis of field hierarchies for status and action purposes."""

from typing import Dict, List
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
