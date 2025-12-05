"""Recommender for copy_from/copy_to actions."""

import logging
from typing import Dict, Optional

from ..conflict_detector import ConflictDetector
from ..inheritance_engine import InheritanceEngine
from ..model.mapping_action_models import ActionInfo, ActionType
from .field_utils import are_types_compatible
from .inherited_recommender import InheritedRecommender

logger = logging.getLogger(__name__)


class CopyRecommender:
    """Generates inherited copy_from/copy_to/extension recommendations."""

    def __init__(
        self,
        mapping,
        fields: dict,
        manual_map: dict,
        inheritance_engine: InheritanceEngine,
        conflict_detector: Optional[ConflictDetector] = None,
    ):
        """Initialize the copy recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
            inheritance_engine: Engine for creating inherited recommendations
            conflict_detector: Detector for conflicts with target fields
        """
        self.mapping = mapping
        self.fields = fields
        self.manual_map = manual_map
        self.inheritance_engine = inheritance_engine
        self.conflict_detector = conflict_detector
        self.inherited_recommender = InheritedRecommender(mapping, fields, manual_map)
        # Dictionary to track fields that are incompatible for copy actions
        # Populated during compute_recommendations()
        self.type_incompatible_fields: Dict[str, str] = {}

    def compute_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute inherited recommendations for copy_from/copy_to/extension actions.
        
        GREEDY BEHAVIOR:
        When a parent field has copy_from, copy_to, or extension action, ALL child fields
        (not just direct children of manually set parents, but recursively)
        should receive recommendations with adjusted other_value.
        
        CONFLICT DETECTION:
        For copy_to recommendations, checks if the target field already has an action.
        If the target field has any action (manual or system-generated), the
        recommendation is NOT created to avoid conflicts.
        
        TYPE COMPATIBILITY:
        Checks if source and target fields have compatible FHIR types.
        Incompatible fields are tracked in self.type_incompatible_fields for
        later use by UseNotUseRecommender.
        
        Only creates recommendations if the action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to inherited recommendation lists
        """
        # Clear the incompatible fields tracking before computing
        self.type_incompatible_fields.clear()
        
        def recommendation_factory_with_conflict_check(
            field_name: str, parent_field_name: str, parent_action: ActionInfo
        ) -> Optional[ActionInfo]:
            """Create recommendation and check for conflicts with target field."""
            recommendation = self.inheritance_engine.create_inherited_recommendation(
                field_name, parent_field_name, parent_action
            )
            
            if not recommendation:
                return None
            
            # Check FHIR type compatibility for copy actions
            target_field_name = recommendation.other_value
            if target_field_name:
                source_field = self.fields.get(field_name)
                target_field = self.fields.get(target_field_name)
                is_compatible, type_warning = are_types_compatible(source_field, target_field)
                
                if not is_compatible:
                    # Types are incompatible - skip copy recommendation and track it
                    reason = (
                        f"Field '{field_name}' -> '{target_field_name}': {type_warning} "
                        f"Copying between fields with incompatible types is not recommended."
                    )
                    self.type_incompatible_fields[field_name] = reason
                    logger.debug(
                        f"Skipping copy recommendation for {field_name} -> {target_field_name}: {type_warning}"
                    )
                    return None
                
                # Add type warning as a remark if there's a compatibility concern
                if type_warning:
                    if recommendation.system_remarks is None:
                        recommendation.system_remarks = []
                    recommendation.system_remarks.append(type_warning)
            
            # For copy_to actions, check if the target field has a fixed value or would be overridden
            if recommendation.action == ActionType.COPY_TO and self.conflict_detector:
                if target_field_name:
                    # First check if target field has a fixed value
                    fixed_value = self.conflict_detector.get_target_fixed_value_info(target_field_name)
                    
                    if fixed_value:
                        # Target has a FIXED value - skip copy recommendation and track it
                        reason = (
                            f"Target field '{target_field_name}' has a fixed value: {fixed_value}. "
                            f"Copying to this field is not possible."
                        )
                        self.type_incompatible_fields[field_name] = reason
                        logger.debug(
                            f"Skipping copy_to recommendation for {field_name} -> {target_field_name}: "
                            f"Target has fixed value: {fixed_value}"
                        )
                        return None
                    
                    # Check for other conflicts (manual actions, etc.)
                    conflict = self.conflict_detector.get_target_field_conflict(
                        field_name, target_field_name, ActionType.COPY_TO
                    )
                    if conflict:
                        # Target has non-FIXED action (manual or other) - skip recommendation entirely
                        logger.debug(
                            f"Skipping copy_to recommendation for {field_name} -> {target_field_name}: "
                            f"Target already has {conflict.action.value if conflict.action else 'unknown'} action"
                        )
                        return None
            
            return recommendation
        
        return self.inherited_recommender.compute_inherited_recommendations(
            action_types={ActionType.COPY_FROM, ActionType.COPY_TO, ActionType.EXTENSION},
            recommendation_factory=recommendation_factory_with_conflict_check
        )
