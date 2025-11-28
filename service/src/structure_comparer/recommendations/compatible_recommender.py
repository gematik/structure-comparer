"""Recommender for compatible fields."""

from typing import Dict

from ..field_hierarchy.field_hierarchy_analyzer import all_descendants_compatible_or_solved
from ..model.mapping_action_models import ActionInfo, ActionSource, ActionType, EvaluationResult
from .field_utils import has_zero_cardinality_in_all_sources


class CompatibleRecommender:
    """Generates USE and USE_RECURSIVE recommendations for compatible fields."""

    def __init__(self, mapping, fields: dict, manual_map: dict):
        """Initialize the compatible recommender.
        
        Args:
            mapping: The mapping object
            fields: Dictionary of all fields
            manual_map: Dictionary of manual entries
        """
        self.mapping = mapping
        self.fields = fields
        self.manual_map = manual_map

    def compute_recommendations(
        self, evaluation_map: Dict[str, EvaluationResult]
    ) -> Dict[str, list[ActionInfo]]:
        """Compute USE and USE_RECURSIVE recommendations for compatible fields.
        
        For compatible fields without manual actions:
        - Recommend USE only if allowed by actions_allowed
        - Additionally recommend USE_RECURSIVE if all descendants are compatible or solved
          AND if USE_RECURSIVE is in actions_allowed
        
        NOTE: Fields with 0..0 cardinality in all source profiles are excluded from
        USE recommendations as they cannot be used.
        
        Args:
            evaluation_map: Dictionary mapping field names to EvaluationResult
        
        Returns:
            Dictionary mapping field names to recommendation lists
        """
        recommendations: Dict[str, list[ActionInfo]] = {}

        for field_name, field in self.fields.items():
            # Skip if field has manual entry
            if field_name in self.manual_map:
                continue

            # Skip if field has 0..0 cardinality in all source profiles
            if has_zero_cardinality_in_all_sources(field, self.mapping):
                continue

            classification = (
                getattr(field, "classification", "unknown")
                if field is not None
                else "unknown"
            )

            # Only create recommendations for compatible fields
            if str(classification).lower() == "compatible":
                # Check if USE action is allowed for this field
                actions_allowed = getattr(field, "actions_allowed", None)
                if actions_allowed is not None:
                    # If actions_allowed is defined, only recommend if USE is in the list
                    if ActionType.USE not in actions_allowed:
                        continue
                
                field_recommendations = [
                    ActionInfo(
                        action=ActionType.USE,
                        source=ActionSource.SYSTEM_DEFAULT,
                        auto_generated=True,
                        system_remark="Recommendation: Field is compatible, suggest using it directly",
                    )
                ]
                
                # Check if USE_RECURSIVE should also be recommended
                # Condition: All descendants must be compatible OR solved
                # AND USE_RECURSIVE must be in actions_allowed (if defined)
                if all_descendants_compatible_or_solved(
                    field_name, self.fields, evaluation_map
                ):
                    # Check if USE_RECURSIVE action is allowed for this field
                    if actions_allowed is None or ActionType.USE_RECURSIVE in actions_allowed:
                        field_recommendations.append(
                            ActionInfo(
                                action=ActionType.USE_RECURSIVE,
                                source=ActionSource.SYSTEM_DEFAULT,
                                auto_generated=True,
                                system_remark=(
                                    "Field and all descendants are compatible or solved; "
                                    "you can safely use USE_RECURSIVE to keep the subtree."
                                ),
                            )
                        )
                
                recommendations[field_name] = field_recommendations

        return recommendations
