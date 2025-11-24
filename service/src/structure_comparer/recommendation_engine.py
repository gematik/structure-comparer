"""Engine for computing recommendations for fields without manual actions."""

import logging
from typing import Dict, List, Mapping, Optional

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
        from .mapping_actions_engine import compute_mapping_actions

        recommendations: Dict[str, list[ActionInfo]] = {}

        # Build action map to know parent actions
        # We need this to find which parents have copy_from/copy_to
        action_map = compute_mapping_actions(self.mapping, self.manual_map)
        
        logger.debug(f"Computing inherited copy recommendations for {len(self.fields)} fields")
        logger.debug(f"Manual entries: {list(self.manual_map.keys())}")
        
        # Log all fields with copy actions
        copy_action_fields = {
            fname: action for fname, action in action_map.items()
            if action.action in {ActionType.COPY_FROM, ActionType.COPY_TO}
        }
        logger.debug(f"Fields with copy actions: {list(copy_action_fields.keys())}")

        # Process fields in depth-sorted order (parents before children)
        ordered_field_names = sorted(self.fields.keys(), key=field_depth)

        for field_name in ordered_field_names:
            # Skip if field has manual entry
            if field_name in self.manual_map:
                logger.debug(f"  {field_name}: Skipping (has manual entry)")
                continue

            # Check all ancestors (not just immediate parent) for copy actions
            parent_field_name = parent_name(field_name)
            found_ancestor = None
            
            while parent_field_name:
                parent_action = action_map.get(parent_field_name)
                
                if parent_action and self.inheritance_engine.is_copy_action(parent_action.action):
                    found_ancestor = parent_field_name
                    logger.debug(
                        f"  {field_name}: Found copy action ancestor: {parent_field_name} "
                        f"({parent_action.action.value})"
                    )
                    
                    # Create inherited recommendation
                    recommendation = self.inheritance_engine.create_inherited_recommendation(
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
                                    logger.debug(
                                        f"    -> Recommendation NOT allowed for field "
                                        f"(actions_allowed={actions_allowed})"
                                    )
                                    break  # Don't check further ancestors
                        
                        logger.debug(
                            f"    -> Created recommendation: {recommendation.action.value} "
                            f"to {recommendation.other_value}"
                        )
                        recommendations[field_name] = [recommendation]
                        break  # Found a copy action, use closest ancestor
                    else:
                        logger.debug("    -> No recommendation created (target field missing?)")
                
                # Move to next ancestor
                parent_field_name = parent_name(parent_field_name)
            
            if not found_ancestor:
                logger.debug(f"  {field_name}: No copy action ancestor found")

        logger.debug(f"Total inherited copy recommendations created: {len(recommendations)}")
        return recommendations

    def _compute_use_recursive_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE recommendations for children of USE_RECURSIVE fields.
        
        GREEDY BEHAVIOR:
        When a parent field has USE_RECURSIVE action (either manual or inherited),
        ALL descendant fields should receive USE recommendations.
        
        Only creates recommendations if the USE action is allowed for the field.
        
        Returns:
            Dictionary mapping field names to USE recommendation lists
        """
        from .mapping_actions_engine import compute_mapping_actions

        recommendations: Dict[str, list[ActionInfo]] = {}

        # Build action map to know which fields have USE_RECURSIVE
        action_map = compute_mapping_actions(self.mapping, self.manual_map)

        # Process fields in depth-sorted order (parents before children)
        ordered_field_names = sorted(self.fields.keys(), key=field_depth)

        for field_name in ordered_field_names:
            # Skip if field has manual entry
            if field_name in self.manual_map:
                continue

            # Check all ancestors for USE_RECURSIVE
            parent_field_name = parent_name(field_name)
            while parent_field_name:
                parent_action = action_map.get(parent_field_name)
                
                if parent_action and parent_action.action == ActionType.USE_RECURSIVE:
                    # Create USE recommendation for this child
                    field = self.fields.get(field_name)
                    if field:
                        actions_allowed = getattr(field, "actions_allowed", None)
                        if actions_allowed is not None:
                            # If actions_allowed is defined, only recommend if USE is allowed
                            if ActionType.USE not in actions_allowed:
                                break  # Don't check further ancestors
                    
                    recommendations[field_name] = [
                        ActionInfo(
                            action=ActionType.USE,
                            source=ActionSource.SYSTEM_DEFAULT,
                            auto_generated=True,
                            system_remark=f"Recommendation: Parent {parent_field_name} has USE_RECURSIVE",
                        )
                    ]
                    break  # Found USE_RECURSIVE, use closest ancestor
                
                # Move to next ancestor
                parent_field_name = parent_name(parent_field_name)

        return recommendations

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
