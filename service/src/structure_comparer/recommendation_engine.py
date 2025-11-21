"""Engine for computing recommendations for fields without manual actions."""

from typing import Dict, Mapping, Optional

from .field_utils import field_depth, parent_name
from .inheritance_engine import InheritanceEngine
from .model.mapping_action_models import ActionInfo, ActionSource, ActionType


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

        # 2. Inherited copy_from/copy_to recommendations
        inherited_recs = self._compute_inherited_copy_recommendations()
        for field_name, recs in inherited_recs.items():
            if field_name in recommendations:
                recommendations[field_name].extend(recs)
            else:
                recommendations[field_name] = recs

        return recommendations

    def _compute_compatible_recommendations(self) -> Dict[str, list[ActionInfo]]:
        """Compute USE recommendations for compatible fields without manual actions.
        
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
        
        When a parent field has copy_from or copy_to action, child fields
        should receive recommendations (not active actions) with adjusted other_value.
        
        Returns:
            Dictionary mapping field names to inherited recommendation lists
        """
        from .mapping_actions_engine import compute_mapping_actions

        recommendations: Dict[str, list[ActionInfo]] = {}

        # Build action map to know parent actions
        # We need this to find which parents have copy_from/copy_to
        action_map = compute_mapping_actions(self.mapping, self.manual_map)

        # Process fields in depth-sorted order (parents before children)
        ordered_field_names = sorted(self.fields.keys(), key=field_depth)

        for field_name in ordered_field_names:
            # Skip if field has manual entry
            if field_name in self.manual_map:
                continue

            parent_field_name = parent_name(field_name)
            if not parent_field_name:
                continue

            parent_action = action_map.get(parent_field_name)
            if not parent_action:
                continue

            # Only create recommendations for copy_from/copy_to inheritance
            if not self.inheritance_engine.is_copy_action(parent_action.action):
                continue

            # Create inherited recommendation
            recommendation = self.inheritance_engine.create_inherited_recommendation(
                field_name, parent_field_name, parent_action
            )

            if recommendation:
                recommendations[field_name] = [recommendation]

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
