"""Engine for computing inherited actions and recommendations for copy_from/copy_to."""

from typing import Dict, Optional

from .field_utils import child_suffix, is_polymorphic_type_choice
from .model.mapping_action_models import ActionInfo, ActionSource, ActionType


class InheritanceEngine:
    """Handles inheritance logic for copy_from/copy_to actions."""

    def __init__(self, all_fields: Dict[str, object]):
        """Initialize the inheritance engine.
        
        Args:
            all_fields: Dictionary mapping field names to field objects
        """
        self.all_fields = all_fields

    def calculate_inherited_other_value(
        self,
        field_name: str,
        parent_field_name: str,
        parent_other_value: str,
    ) -> Optional[str]:
        """Calculate the inherited other_value for a child field.
        
        When a parent field has a copy_from/copy_to action with an other_value,
        child fields should inherit the same action with an adjusted other_value.
        
        For example:
        - Parent: "Medication.extension:A" -> "Medication.extension:B"
        - Child: "Medication.extension:A.url" -> "Medication.extension:B.url"
        
        Args:
            field_name: The child field name
            parent_field_name: The parent field name
            parent_other_value: The parent's other_value
            
        Returns:
            The calculated other_value for the child field, or None if invalid
        """
        if not parent_other_value:
            return None

        # Extract the child suffix (e.g., ".system" or ".code")
        suffix = child_suffix(field_name, parent_field_name)

        # Don't inherit for polymorphic type choices (e.g., :valueBoolean)
        # These are concrete type implementations, not structural children
        if is_polymorphic_type_choice(suffix):
            return None

        # Append the same suffix to the parent's other_value
        candidate_other_value = parent_other_value + suffix

        # Validate that the target field actually exists
        target_exists = candidate_other_value in self.all_fields

        # Handle polymorphic value[x] fields specially
        if not target_exists and ".value[x]" in parent_other_value:
            candidate_other_value = self._handle_polymorphic_value_field(
                parent_other_value, suffix
            )
            if candidate_other_value:
                target_exists = True

        return candidate_other_value if target_exists else None

    def _handle_polymorphic_value_field(
        self, parent_other_value: str, suffix: str
    ) -> Optional[str]:
        """Handle polymorphic value[x] fields when finding inherited other_value.
        
        If the direct target doesn't exist and the parent is a polymorphic value[x],
        try to find matching type choices (e.g., :valueCoding, :valueString).
        
        Args:
            parent_other_value: The parent's other_value containing .value[x]
            suffix: The child suffix to append
            
        Returns:
            The adjusted other_value if a valid type choice is found, None otherwise
        """
        # Look for type choices (e.g., :valueCoding, :valueString)
        type_choices = [
            f
            for f in self.all_fields.keys()
            if f.startswith(parent_other_value + ":")
            and f.count(":") == parent_other_value.count(":") + 1
        ]

        # Try each type choice with the child suffix
        for type_choice in type_choices:
            alternative_target = type_choice + suffix
            if alternative_target in self.all_fields:
                return alternative_target

        return None

    def can_inherit_action(self, action_type: Optional[ActionType]) -> bool:
        """Check if an action type can be inherited by child fields.
        
        Args:
            action_type: The action type to check
            
        Returns:
            True if the action can be inherited, False otherwise
        """
        if action_type is None:
            return False

        inheritable_actions = {
            ActionType.NOT_USE,
            ActionType.EMPTY,
            ActionType.USE_RECURSIVE,
            ActionType.COPY_FROM,
            ActionType.COPY_TO,
        }
        return action_type in inheritable_actions

    def is_copy_action(self, action_type: Optional[ActionType]) -> bool:
        """Check if an action type is a copy action (copy_from or copy_to).
        
        Args:
            action_type: The action type to check
            
        Returns:
            True if the action is copy_from or copy_to, False otherwise
        """
        if action_type is None:
            return False
        return action_type in {ActionType.COPY_FROM, ActionType.COPY_TO}

    def create_inherited_recommendation(
        self,
        field_name: str,
        parent_field_name: str,
        parent_action: ActionInfo,
    ) -> Optional[ActionInfo]:
        """Create an inherited recommendation for copy_from/copy_to actions.
        
        Args:
            field_name: The child field name
            parent_field_name: The parent field name
            parent_action: The parent's action info
            
        Returns:
            An ActionInfo representing the inherited recommendation, or None if invalid
        """
        if not self.is_copy_action(parent_action.action):
            return None

        # Calculate the inherited other_value
        inherited_other_value = self.calculate_inherited_other_value(
            field_name, parent_field_name, parent_action.other_value
        )

        if not inherited_other_value:
            return None

        return ActionInfo(
            action=parent_action.action,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark=f"Inherited recommendation from {parent_field_name}",
            other_value=inherited_other_value,
        )
