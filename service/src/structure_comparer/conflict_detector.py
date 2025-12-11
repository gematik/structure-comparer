"""Conflict detection for mapping actions and recommendations.

This module provides utilities to detect conflicts where recommendations
would override existing actions (manual or system-generated).
"""

from typing import Dict, Optional

from .model.mapping_action_models import ActionInfo, ActionType


class ConflictDetector:
    """Detects conflicts between recommendations and existing actions.
    
    A conflict occurs when:
    1. A field already has an active action (manual or system-generated)
    2. A recommendation would change or override this action
    
    Special case: copy_value_to/copy_value_from recommendations
    - When recommending copy_value_to X.field, check if X.field already has an action
    - When recommending copy_value_from Y.field, check if current field already has an action
    """
    
    def __init__(self, action_map: Dict[str, ActionInfo]):
        """Initialize the conflict detector.
        
        Args:
            action_map: Dictionary mapping field names to their current ActionInfo
        """
        self.action_map = action_map
    
    def has_active_action(self, field_name: str) -> bool:
        """Check if a field has an active action (not just None/default).
        
        Args:
            field_name: The field to check
            
        Returns:
            True if the field has an active action, False otherwise
        """
        action_info = self.action_map.get(field_name)
        if action_info is None:
            return False
        
        # None action means no action selected yet (user must decide)
        return action_info.action is not None
    
    def would_override_action(
        self,
        field_name: str,
        recommended_action: ActionType,
        recommended_other_value: Optional[str] = None
    ) -> bool:
        """Check if applying a recommendation would override an existing action.
        
        Args:
            field_name: The field for which the recommendation is made
            recommended_action: The recommended action type
            recommended_other_value: The other_value for copy actions
            
        Returns:
            True if the recommendation would override an existing action
        """
        action_info = self.action_map.get(field_name)
        
        # No existing action -> no conflict
        if action_info is None or action_info.action is None:
            return False
        
        # Same action with same parameters -> no conflict
        if action_info.action == recommended_action:
            # For copy actions, also check other_value
            if recommended_action in {ActionType.COPY_VALUE_FROM, ActionType.COPY_VALUE_TO}:
                return action_info.other_value != recommended_other_value
            # For other actions, same action type means no conflict
            return False
        
        # Different action -> conflict
        return True
    
    def get_target_field_conflict(
        self,
        source_field: str,
        target_field: str,
        action_type: ActionType
    ) -> Optional[ActionInfo]:
        """Check if a copy_value_to action would conflict with the target field's action.
        
        For copy_value_to recommendations, we need to check if the TARGET field
        already has an action that would be overridden.
        
        Args:
            source_field: The source field (where recommendation is shown)
            target_field: The target field (where data would be copied to)
            action_type: The action type (should be COPY_VALUE_TO)
            
        Returns:
            The conflicting ActionInfo if a conflict exists, None otherwise
        """
        if action_type != ActionType.COPY_VALUE_TO:
            return None
        
        # Check if target field has an active action
        target_action = self.action_map.get(target_field)
        if target_action is None or target_action.action is None:
            return None
        
        # Target has an action -> this would be a conflict
        return target_action
    
    def get_target_fixed_value_info(self, target_field: str) -> Optional[str]:
        """Get fixed value information for a target field.
        
        If the target field has a FIXED action with a fixed value,
        returns a formatted string describing the fixed value.
        
        Args:
            target_field: The target field to check
            
        Returns:
            A string describing the fixed value, or None if no fixed value
        """
        target_action = self.action_map.get(target_field)
        if target_action is None:
            return None
        
        # Check if it's a FIXED action with a fixed value
        # Fixed values are stored in the `fixed_value` attribute, not `other_value`
        if target_action.action == ActionType.FIXED:
            fixed_val = getattr(target_action, 'fixed_value', None)
            if fixed_val is not None:
                return str(fixed_val)
        
        return None
    
    def get_conflict_message(
        self,
        field_name: str,
        recommended_action: ActionType,
        conflicting_action: ActionInfo
    ) -> str:
        """Generate a user-friendly message explaining the conflict.
        
        Args:
            field_name: The field name
            recommended_action: The recommended action that conflicts
            conflicting_action: The existing action causing the conflict
            
        Returns:
            A descriptive message explaining the conflict
        """
        action_type = conflicting_action.action.value if conflicting_action.action else "unknown"
        
        if conflicting_action.auto_generated:
            return (
                f"Cannot apply recommendation: Field '{field_name}' already has "
                f"a system-generated {action_type.upper()} action."
            )
        else:
            return (
                f"Cannot apply recommendation: Field '{field_name}' already has "
                f"a manually configured {action_type.upper()} action."
            )
