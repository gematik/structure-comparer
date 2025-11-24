"""Recommender for fields with 0..0 cardinality."""

from typing import Dict

from ..model.mapping_action_models import ActionInfo, ActionSource, ActionType
from .field_utils import has_zero_cardinality_in_all_sources


class ZeroCardinalityRecommender:
    """Generates NOT_USE recommendations for fields with 0..0 cardinality in all sources."""

    def __init__(self, mapping, fields: dict, manual_map: dict):
        """Initialize the zero cardinality recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
        """
        self.mapping = mapping
        self.fields = fields
        self.manual_map = manual_map

    def compute_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute NOT_USE recommendations for fields with 0..0 cardinality in ALL source profiles.
        
        When a field has cardinality 0..0 in all source profiles, it means the field
        cannot be used in any source and should therefore have a NOT_USE action.
        
        Only creates recommendations if:
        - The field exists in at least one source profile
        - ALL source profiles where the field exists have cardinality 0..0
        - The field doesn't already have a manual entry
        - NOT_USE action is allowed for the field
        
        Returns:
            Dictionary mapping field names to NOT_USE recommendation lists
        """
        recommendations: Dict[str, list[ActionInfo]] = {}

        for field_name, field in self.fields.items():
            # Skip if field has manual entry
            if field_name in self.manual_map:
                continue

            # Check if field has 0..0 cardinality in all source profiles
            if not has_zero_cardinality_in_all_sources(field, self.mapping):
                continue

            # Check if NOT_USE action is allowed for this field
            actions_allowed = getattr(field, "actions_allowed", None)
            if actions_allowed is not None and ActionType.NOT_USE not in actions_allowed:
                continue

            # Create NOT_USE recommendation
            recommendations[field_name] = [
                ActionInfo(
                    action=ActionType.NOT_USE,
                    source=ActionSource.SYSTEM_DEFAULT,
                    auto_generated=True,
                    system_remark=(
                        "Field has cardinality 0..0 in all source profiles; "
                        "it cannot be used and should be marked as NOT_USE."
                    ),
                )
            ]

        return recommendations
