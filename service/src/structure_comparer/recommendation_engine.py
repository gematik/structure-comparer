"""Engine for computing recommendations for fields without manual actions."""

import logging
from typing import Callable, Dict, Mapping, Optional

from .conflict_detector import ConflictDetector
from .field_hierarchy import field_depth, parent_name
from .field_hierarchy.field_hierarchy_analyzer import all_descendants_compatible_or_solved
from .inheritance_engine import InheritanceEngine
from .mapping_evaluation_engine import evaluate_mapping
from .model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationResult,
)

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
        self.conflict_detector: Optional[ConflictDetector] = None  # Will be set when action_map is available

    def compute_all_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute all recommendations for the mapping.
        
        Returns:
            Dictionary mapping field names to lists of ActionInfo recommendations
        """
        # First, compute the action map to enable conflict detection
        from .mapping_actions_engine import compute_mapping_actions
        action_map = compute_mapping_actions(self.mapping, self.manual_map)
        self.conflict_detector = ConflictDetector(action_map)
        
        # Compute evaluation map for use in recommendations
        evaluation_map: Dict[str, EvaluationResult] = evaluate_mapping(self.mapping, action_map)
        
        recommendations: Dict[str, list[ActionInfo]] = {}

        # 1. Compatible field recommendations (USE action and USE_RECURSIVE)
        compatible_recs = self._compute_compatible_recommendations(evaluation_map)
        for field_name, recs in compatible_recs.items():
            recommendations[field_name] = recs

        # 2. Inherited copy_from/copy_to recommendations (greedy for all children)
        # Now with conflict detection to avoid overriding existing actions
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

    def _compute_compatible_recommendations(
        self, evaluation_map: Dict[str, EvaluationResult]
    ) -> Dict[str, list[ActionInfo]]:
        """Compute USE and USE_RECURSIVE recommendations for compatible fields.
        
        For compatible fields without manual actions:
        - Recommend USE only if allowed by actions_allowed
        - Additionally recommend USE_RECURSIVE if all descendants are compatible or solved
          AND if USE_RECURSIVE is in actions_allowed
        
        IMPORTANT: Recommendations are filtered by actions_allowed.
        The actions_allowed controls what actions can be manually set, and recommendations
        should only suggest actions that are actually allowed for the field.
        
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
        
        CONFLICT DETECTION:
        For copy_to recommendations, checks if the target field already has an action.
        If the target field has any action (manual or system-generated), the
        recommendation is NOT created to avoid conflicts.
        
        Only creates recommendations if the action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to inherited recommendation lists
        """
        def recommendation_factory_with_conflict_check(
            field_name: str, parent_field_name: str, parent_action: ActionInfo
        ) -> Optional[ActionInfo]:
            """Create recommendation and check for conflicts with target field."""
            recommendation = self.inheritance_engine.create_inherited_recommendation(
                field_name, parent_field_name, parent_action
            )
            
            if not recommendation:
                return None
            
            # For copy_to actions, check if the target field has a fixed value or would be overridden
            if recommendation.action == ActionType.COPY_TO and self.conflict_detector:
                target_field = recommendation.other_value
                if target_field:
                    # First check if target field has a fixed value
                    fixed_value = self.conflict_detector.get_target_fixed_value_info(target_field)
                    
                    if fixed_value:
                        # Target has a FIXED value - return NOT_USE recommendation instead
                        warning_remark = (
                            f"Target field '{target_field}' has a fixed value: {fixed_value}. "
                            f"Copying to this field is not possible. Recommend NOT_USE for this field."
                        )
                        return ActionInfo(
                            action=ActionType.NOT_USE,
                            source=ActionSource.SYSTEM_DEFAULT,
                            auto_generated=True,
                            system_remarks=[warning_remark],
                        )
                    
                    # Check for other conflicts (manual actions, etc.)
                    conflict = self.conflict_detector.get_target_field_conflict(
                        field_name, target_field, ActionType.COPY_TO
                    )
                    if conflict:
                        # Target has non-FIXED action (manual or other) - skip recommendation entirely
                        logger.debug(
                            f"Skipping copy_to recommendation for {field_name} -> {target_field}: "
                            f"Target already has {conflict.action.value if conflict.action else 'unknown'} action"
                        )
                        return None
            
            return recommendation
        
        return self._compute_inherited_recommendations(
            action_types={ActionType.COPY_FROM, ActionType.COPY_TO},
            recommendation_factory=recommendation_factory_with_conflict_check
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
