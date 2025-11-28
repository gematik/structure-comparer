"""Recommender for USE_RECURSIVE actions."""

from typing import Dict

from ..model.mapping_action_models import ActionInfo, ActionSource, ActionType
from .inherited_recommender import InheritedRecommender


class UseRecursiveRecommender:
    """Generates USE recommendations for children of USE_RECURSIVE fields."""

    def __init__(self, mapping, fields: dict, manual_map: dict):
        """Initialize the USE_RECURSIVE recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
        """
        self.inherited_recommender = InheritedRecommender(mapping, fields, manual_map)

    def compute_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE recommendations for children of USE_RECURSIVE fields.
        
        GREEDY BEHAVIOR:
        When a parent field has USE_RECURSIVE action (either manual or inherited),
        ALL descendant fields should receive USE recommendations.
        
        Only creates recommendations if the USE action is allowed for the field.
        
        NOTE: Fields with 0..0 cardinality in all source profiles are excluded.
        
        Returns:
            Dictionary mapping field names to USE recommendation lists
        """
        return self.inherited_recommender.compute_inherited_recommendations(
            action_types={ActionType.USE_RECURSIVE},
            recommendation_factory=lambda field_name, parent_field_name, parent_action:
                ActionInfo(
                    action=ActionType.USE,
                    source=ActionSource.SYSTEM_DEFAULT,
                    auto_generated=True,
                    system_remark=f"Recommendation: Parent {parent_field_name} has USE_RECURSIVE",
                )
        )
