"""Recommender for inherited actions from parent fields."""

import logging
from typing import Callable, Dict, Optional

from ..field_hierarchy import field_depth, parent_name
from ..model.mapping_action_models import ActionInfo, ActionType
from .field_utils import has_zero_cardinality_in_all_sources

logger = logging.getLogger(__name__)


class InheritedRecommender:
    """Generates recommendations based on parent field actions."""

    def __init__(self, mapping, fields: dict, manual_map: dict):
        """Initialize the inherited recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
        """
        self.mapping = mapping
        self.fields = fields
        self.manual_map = manual_map

    def compute_inherited_recommendations(
        self,
        action_types: set[ActionType],
        recommendation_factory: Callable[[str, str, ActionInfo], Optional[ActionInfo]],
    ) -> Dict[str, list[ActionInfo]]:
        """Generic method to compute inherited recommendations for specified action types.
        
        GREEDY BEHAVIOR:
        When a parent field has an action in action_types, ALL descendant fields
        should receive recommendations created by recommendation_factory.
        
        Only creates recommendations if the action is allowed for the field.
        
        Args:
            action_types: Set of action types to look for in ancestors
            recommendation_factory: Function that creates recommendation from
                (field_name, parent_field_name, parent_action) -> Optional[ActionInfo]
        
        Returns:
            Dictionary mapping field names to inherited recommendation lists
        """
        from ..mapping_actions_engine import compute_mapping_actions

        recommendations: Dict[str, list[ActionInfo]] = {}

        # Build action map to know parent actions
        action_map = compute_mapping_actions(self.mapping, self.manual_map)

        # Process fields in depth-sorted order (parents before children)
        ordered_field_names = sorted(self.fields.keys(), key=field_depth)

        for field_name in ordered_field_names:
            # Skip if field has manual entry
            if field_name in self.manual_map:
                continue

            # Skip if field has 0..0 cardinality in all source profiles
            field = self.fields.get(field_name)
            if field and has_zero_cardinality_in_all_sources(field, self.mapping):
                continue

            # Check all ancestors for actions in action_types
            parent_field_name = parent_name(field_name)
            while parent_field_name:
                parent_action = action_map.get(parent_field_name)

                if parent_action and parent_action.action in action_types:
                    # Create recommendation using the factory
                    recommendation = recommendation_factory(
                        field_name, parent_field_name, parent_action
                    )

                    if recommendation:
                        # Check if the recommended action is allowed for this field
                        field = self.fields.get(field_name)
                        if field:
                            actions_allowed = getattr(field, "actions_allowed", None)
                            if actions_allowed is not None:
                                # If actions_allowed is defined, only recommend if action is allowed
                                if recommendation.action not in actions_allowed:
                                    break  # Don't check further ancestors

                        recommendations[field_name] = [recommendation]
                        break  # Found an action, use closest ancestor

                # Move to next ancestor
                parent_field_name = parent_name(parent_field_name)

        return recommendations
