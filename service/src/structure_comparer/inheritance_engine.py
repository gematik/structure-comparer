"""Engine for computing inherited actions and recommendations for copy_from/copy_to."""

from typing import Dict, Optional

from .field_hierarchy import child_suffix, is_polymorphic_type_choice
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
    ) -> Optional[tuple[str, bool]]:
        """Calculate the inherited other_value for a child field.
        
        When a parent field has a copy_from/copy_to action with an other_value,
        child fields should inherit the same action with an adjusted other_value.
        
        For example:
        - Parent: "Medication.extension:A" -> "Medication.extension:B"
        - Child: "Medication.extension:A.url" -> "Medication.extension:B.url"
        
        For sliced fields without explicit children, falls back to the base type:
        - Parent: "Practitioner.identifier:ANR" -> "Practitioner.identifier:LANR"
        - Child: "Practitioner.identifier:ANR.id" -> "Practitioner.identifier:LANR.id"
          (if LANR.id doesn't exist, try Practitioner.identifier.id as fallback)
        
        Args:
            field_name: The child field name
            parent_field_name: The parent field name
            parent_other_value: The parent's other_value
            
        Returns:
            A tuple of (other_value, is_implicit_slice) where:
            - other_value: The calculated other_value for the child field
            - is_implicit_slice: True if target field is not explicitly defined but
              structurally valid (inherits from base type), False otherwise
            Returns None if the target is invalid
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
        is_implicit_slice = False  # Track if target is implicitly valid but not explicitly defined

        # Handle polymorphic value[x] fields specially
        if not target_exists and ".value[x]" in parent_other_value:
            candidate_other_value = self._handle_polymorphic_value_field(
                parent_other_value, suffix
            )
            if candidate_other_value:
                target_exists = True

        # Fallback for sliced fields
        if not target_exists and ":" in parent_field_name:
            # Source field is sliced (e.g., Organization.telecom:telefon)
            # Check if parent target is NOT sliced (e.g., Organization.telecom)
            target_is_not_sliced = ":" not in parent_other_value
            
            if target_is_not_sliced:
                # Mapping from sliced source to non-sliced target
                # If the source child exists, the target child should be structurally valid
                # even if not explicitly defined (target inherits from base FHIR type)
                if field_name in self.all_fields:
                    # Source child exists, so target child should be structurally compatible
                    target_exists = True
                    is_implicit_slice = True
            elif ":" in parent_other_value:
                # Both parent and target are slices of the same base type
                # Check if the parent slice itself exists and has this child
                if parent_field_name in self.all_fields and field_name in self.all_fields:
                    # The source field exists, so the target should be structurally compatible
                    # even if not explicitly defined (FHIR slices inherit from base type)
                    target_exists = True
                    is_implicit_slice = True  # Mark as implicit since target slice child doesn't exist explicitly
            
            # If still not found, try base field fallback
            if not target_exists:
                base_other_value = self._get_base_field_name(parent_other_value)
                if base_other_value:
                    fallback_candidate = base_other_value + suffix
                    if fallback_candidate in self.all_fields:
                        # The base field exists, so we can use the sliced target
                        target_exists = True
                        is_implicit_slice = True  # Mark as implicit

        return (candidate_other_value, is_implicit_slice) if target_exists else None

    def _get_base_field_name(self, sliced_field_name: str) -> Optional[str]:
        """Get the base field name without slice suffix.
        
        For example:
        - "Practitioner.identifier:LANR" -> "Practitioner.identifier"
        - "Medication.extension:A" -> "Medication.extension"
        
        Args:
            sliced_field_name: Field name potentially containing a slice (colon)
            
        Returns:
            Base field name without slice, or None if not a sliced field
        """
        if ":" not in sliced_field_name:
            return None
        
        # Find the last colon (slice marker)
        last_colon = sliced_field_name.rfind(":")
        base_name = sliced_field_name[:last_colon]
        
        return base_name

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
            # ActionType.NOT_USE,  # Removed: Now handled as recommendation only
            ActionType.EMPTY,
            ActionType.USE_RECURSIVE,
            ActionType.COPY_FROM,
            ActionType.COPY_TO,
            ActionType.EXTENSION,  # Extension actions should be inherited to child fields
        }
        return action_type in inheritable_actions

    def is_copy_action(self, action_type: Optional[ActionType]) -> bool:
        """Check if an action type is a copy action (copy_from, copy_to, or extension).
        
        Args:
            action_type: The action type to check
            
        Returns:
            True if the action is copy_from, copy_to, or extension, False otherwise
        """
        if action_type is None:
            return False
        return action_type in {ActionType.COPY_FROM, ActionType.COPY_TO, ActionType.EXTENSION}

    def create_inherited_recommendation(
        self,
        field_name: str,
        parent_field_name: str,
        parent_action: ActionInfo,
    ) -> Optional[ActionInfo]:
        """Create an inherited recommendation for copy_from/copy_to/extension actions.
        
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
        result = self.calculate_inherited_other_value(
            field_name, parent_field_name, parent_action.other_value
        )

        if not result:
            return None

        inherited_other_value, is_implicit_slice = result

        # Create appropriate remarks based on whether target is implicitly valid
        if is_implicit_slice:
            remarks = [
                f"Inherited from {parent_field_name}.",
                "Target field not explicitly defined in profile but structurally valid (inherits from base type)."
            ]
        else:
            remarks = [f"Inherited recommendation from {parent_field_name}"]

        return ActionInfo(
            action=parent_action.action,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remarks=remarks,
            other_value=inherited_other_value,
        )
