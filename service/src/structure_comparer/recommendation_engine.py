"""Engine for computing recommendations for fields without manual actions."""

import logging
from typing import Callable, Dict, List, Mapping, Optional

from .field_utils import field_depth, get_direct_children, parent_name
from .inheritance_engine import InheritanceEngine
from .model.mapping_action_models import ActionInfo, ActionSource, ActionType

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Computes recommendations for fields that have no active manual actions."""

    def __init__(self, mapping, manual_entries: Optional[Mapping[str, dict]] = None):
        """Initialize the recommendation engine.
        
        Args:
            mapping: The mapping object containing fields
            manual_entries: Optional dictionary of manual field entries
        """
        self.mapping = mapping
        self.fields = getattr(mapping, "fields", {}) or {}
        self.manual_map = self._normalize_manual_entries(manual_entries)
        self.inheritance_engine = InheritanceEngine(self.fields)

    def compute_all_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute all recommendations for the mapping.
        
        Returns:
            Dictionary mapping field names to lists of ActionInfo recommendations
        """
        recommendations: Dict[str, list[ActionInfo]] = {}

        # 1. Compatible field recommendations (USE action)
        compatible_recs = self._compute_compatible_recommendations()
        for field_name, recs in compatible_recs.items():
            recommendations[field_name] = recs

        # 2. Inherited copy_from/copy_to recommendations (greedy for all children)
        inherited_recs = self._compute_inherited_copy_recommendations()
        for field_name, recs in inherited_recs.items():
            if field_name in recommendations:
                recommendations[field_name].extend(recs)
            else:
                recommendations[field_name] = recs

        # 3. USE_RECURSIVE recommendations (greedy for all children)
        use_recursive_recs = self._compute_use_recursive_recommendations()
        for field_name, recs in use_recursive_recs.items():
            if field_name in recommendations:
                recommendations[field_name].extend(recs)
            else:
                recommendations[field_name] = recs

        # 4. USE/NOT_USE recommendations (greedy for all children)
        use_not_use_recs = self._compute_use_not_use_recommendations()
        for field_name, recs in use_not_use_recs.items():
            if field_name in recommendations:
                recommendations[field_name].extend(recs)
            else:
                recommendations[field_name] = recs

        return recommendations

    def _compute_compatible_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE recommendations for compatible fields without manual actions.
        
        Only creates recommendations if the USE action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to USE recommendation lists
        """
        recommendations: Dict[str, list[ActionInfo]] = {}

        for field_name, field in self.fields.items():
            # Skip if field has manual entry
            if field_name in self.manual_map:
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
                
                recommendations[field_name] = [
                    ActionInfo(
                        action=ActionType.USE,
                        source=ActionSource.SYSTEM_DEFAULT,
                        auto_generated=True,
                        system_remark="Recommendation: Field is compatible, suggest using it directly",
                    )
                ]

        return recommendations

    def _compute_inherited_recommendations(
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
        from .mapping_actions_engine import compute_mapping_actions

        recommendations: Dict[str, list[ActionInfo]] = {}

        # Build action map to know parent actions
        action_map = compute_mapping_actions(self.mapping, self.manual_map)

        # Process fields in depth-sorted order (parents before children)
        ordered_field_names = sorted(self.fields.keys(), key=field_depth)

        for field_name in ordered_field_names:
            # Skip if field has manual entry
            if field_name in self.manual_map:
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

    def _compute_inherited_copy_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute inherited recommendations for copy_from/copy_to actions.
        
        GREEDY BEHAVIOR:
        When a parent field has copy_from or copy_to action, ALL child fields
        (not just direct children of manually set parents, but recursively)
        should receive recommendations with adjusted other_value.
        
        Only creates recommendations if the action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to inherited recommendation lists
        """
        return self._compute_inherited_recommendations(
            action_types={ActionType.COPY_FROM, ActionType.COPY_TO},
            recommendation_factory=lambda field_name, parent_field_name, parent_action:
                self.inheritance_engine.create_inherited_recommendation(
                    field_name, parent_field_name, parent_action
                )
        )

    def _compute_use_recursive_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE recommendations for children of USE_RECURSIVE fields.
        
        GREEDY BEHAVIOR:
        When a parent field has USE_RECURSIVE action (either manual or inherited),
        ALL descendant fields should receive USE recommendations.
        
        Only creates recommendations if the USE action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to USE recommendation lists
        """
        return self._compute_inherited_recommendations(
            action_types={ActionType.USE_RECURSIVE},
            recommendation_factory=lambda field_name, parent_field_name, parent_action:
                ActionInfo(
                    action=ActionType.USE,
                    source=ActionSource.SYSTEM_DEFAULT,
                    auto_generated=True,
                    system_remark=f"Recommendation: Parent {parent_field_name} has USE_RECURSIVE",
                )
        )

    def _compute_use_not_use_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE/NOT_USE recommendations for children of USE/NOT_USE fields.
        
        GREEDY BEHAVIOR:
        When a parent field has USE or NOT_USE action, ALL descendant fields
        should receive corresponding recommendations.
        
        Only creates recommendations if the action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to USE/NOT_USE recommendation lists
        """
        return self._compute_inherited_recommendations(
            action_types={ActionType.USE, ActionType.NOT_USE},
            recommendation_factory=lambda field_name, parent_field_name, parent_action:
                ActionInfo(
                    action=parent_action.action,  # Inherit the same action (USE or NOT_USE)
                    source=ActionSource.SYSTEM_DEFAULT,
                    auto_generated=True,
                    system_remarks=[f"Inherited recommendation from {parent_field_name}"],
                )
        )

    def _normalize_manual_entries(
        self, manual_entries: Optional[Mapping[str, dict]]
    ) -> Dict[str, dict]:
        """Normalize manual entries to a consistent dictionary format.
        
        Args:
            manual_entries: Raw manual entries in various formats
            
        Returns:
            Normalized dictionary mapping field names to entry data
        """
        if not manual_entries:
            return {}

        # If we are given a Pydantic model or similar with a `fields` attribute
        if not isinstance(manual_entries, Mapping) and hasattr(
            manual_entries, "fields"
        ):
            field_entries = getattr(manual_entries, "fields", [])
            normalized: Dict[str, dict] = {}
            for entry in field_entries or []:
                if hasattr(entry, "model_dump"):
                    payload = entry.model_dump()
                elif isinstance(entry, Mapping):
                    payload = dict(entry)
                else:
                    payload = entry.__dict__.copy()
                name = payload.get("name")
                if not name:
                    continue
                # Skip auto-generated entries (they are not manual decisions)
                if payload.get("auto_generated"):
                    continue
                normalized[name] = payload
            return normalized

        # Handle regular dictionary input
        cleaned: Dict[str, dict] = {}
        for name, data in manual_entries.items():
            payload = dict(data) if isinstance(data, Mapping) else data
            # Skip auto-generated entries
            if payload.get("auto_generated"):
                continue
            cleaned[name] = payload
        return cleaned
