"""Recommender for USE/NOT_USE actions."""

from typing import Dict

from ..model.mapping_action_models import ActionInfo, ActionSource, ActionType
from .inherited_recommender import InheritedRecommender


class UseNotUseRecommender:
    """Generates USE/NOT_USE recommendations for children of USE/NOT_USE fields."""

    def __init__(self, mapping, fields: dict, manual_map: dict):
        """Initialize the USE/NOT_USE recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
        """
        self.inherited_recommender = InheritedRecommender(mapping, fields, manual_map)

    def compute_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE/NOT_USE recommendations for children of USE/NOT_USE fields.
        
        GREEDY BEHAVIOR:
        When a parent field has USE or NOT_USE action, ALL descendant fields
        should receive corresponding recommendations.
        
        Only creates recommendations if the action is allowed for the field.
        
        NOTE: Fields with 0..0 cardinality in all source profiles are excluded.
        
        Returns:
            Dictionary mapping field names to USE/NOT_USE recommendation lists
        """
        return self.inherited_recommender.compute_inherited_recommendations(
            action_types={ActionType.USE, ActionType.NOT_USE},
            recommendation_factory=lambda field_name, parent_field_name, parent_action:
                ActionInfo(
                    action=parent_action.action,  # Inherit the same action (USE or NOT_USE)
                    source=ActionSource.SYSTEM_DEFAULT,
                    auto_generated=True,
                    system_remarks=[f"Inherited recommendation from {parent_field_name}"],
                )
        )
