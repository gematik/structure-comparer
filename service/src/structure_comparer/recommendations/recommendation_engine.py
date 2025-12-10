"""Engine for computing recommendations for fields without manual actions."""

import logging
from typing import Dict, Mapping, Optional

from ..conflict_detector import ConflictDetector
from ..inheritance_engine import InheritanceEngine
from ..mapping_evaluation_engine import evaluate_mapping
from ..model.mapping_action_models import ActionInfo, EvaluationResult
from .compatible_recommender import CompatibleRecommender
from .copy_recommender import CopyRecommender
from .use_not_use_recommender import UseNotUseRecommender
from .use_recursive_recommender import UseRecursiveRecommender
from .zero_cardinality_recommender import ZeroCardinalityRecommender

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
        from ..mapping_actions_engine import compute_mapping_actions
        action_map = compute_mapping_actions(self.mapping, self.manual_map)
        self.conflict_detector = ConflictDetector(action_map)
        
        # Compute evaluation map for use in recommendations
        evaluation_map: Dict[str, EvaluationResult] = evaluate_mapping(self.mapping, action_map)
        
        recommendations: Dict[str, list[ActionInfo]] = {}

        # 1. Compatible field recommendations (USE action and USE_RECURSIVE)
        compatible_recommender = CompatibleRecommender(self.mapping, self.fields, self.manual_map)
        compatible_recs = compatible_recommender.compute_recommendations(evaluation_map)
        self._merge_recommendations(recommendations, compatible_recs)

        # 2. Inherited copy_value_from/copy_value_to recommendations (greedy for all children)
        copy_recommender = CopyRecommender(
            self.mapping, self.fields, self.manual_map,
            self.inheritance_engine, self.conflict_detector
        )
        inherited_recs = copy_recommender.compute_recommendations()
        self._merge_recommendations(recommendations, inherited_recs)

        # 3. USE_RECURSIVE recommendations (greedy for all children)
        use_recursive_recommender = UseRecursiveRecommender(self.mapping, self.fields, self.manual_map)
        use_recursive_recs = use_recursive_recommender.compute_recommendations()
        self._merge_recommendations(recommendations, use_recursive_recs)

        # 4. USE/NOT_USE recommendations (greedy for all children)
        # Pass copy_recommender to enable NOT_USE for type-incompatible fields
        use_not_use_recommender = UseNotUseRecommender(
            self.mapping, self.fields, self.manual_map, copy_recommender
        )
        use_not_use_recs = use_not_use_recommender.compute_recommendations()
        self._merge_recommendations(recommendations, use_not_use_recs)

        # 5. NOT_USE recommendations for fields with 0..0 cardinality in all source profiles
        zero_cardinality_recommender = ZeroCardinalityRecommender(self.mapping, self.fields, self.manual_map)
        zero_cardinality_recs = zero_cardinality_recommender.compute_recommendations()
        self._merge_recommendations(recommendations, zero_cardinality_recs)

        # Remove duplicate recommendations by action type
        for field_name in recommendations:
            recommendations[field_name] = self._deduplicate_recommendations(
                recommendations[field_name]
            )

        return recommendations

    def _merge_recommendations(
        self,
        target: Dict[str, list[ActionInfo]],
        source: Dict[str, list[ActionInfo]]
    ) -> None:
        """Merge recommendations from source into target dictionary.
        
        Args:
            target: Target dictionary to merge into
            source: Source dictionary to merge from
        """
        for field_name, recs in source.items():
            if field_name in target:
                target[field_name].extend(recs)
            else:
                target[field_name] = recs

    def _deduplicate_recommendations(
        self, recommendations: list[ActionInfo]
    ) -> list[ActionInfo]:
        """Remove duplicate recommendations by action type.
        
        Keeps only the first occurrence of each action type.
        This ensures that a field doesn't get multiple recommendations
        for the same action type from different sources.
        
        Args:
            recommendations: List of ActionInfo recommendations that may contain duplicates
            
        Returns:
            Deduplicated list of recommendations
        """
        seen_actions = set()
        deduplicated = []
        
        for rec in recommendations:
            if rec.action not in seen_actions:
                seen_actions.add(rec.action)
                deduplicated.append(rec)
        
        return deduplicated

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
