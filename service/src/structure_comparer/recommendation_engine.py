"""Backward compatibility module for recommendation engine.

This module re-exports the RecommendationEngine from the new recommendations package.
"""

from .recommendations.recommendation_engine import RecommendationEngine

__all__ = ["RecommendationEngine"]


# Legacy class definition for backward compatibility
class _LegacyRecommendationEngine(RecommendationEngine):
    """Legacy compatibility class - do not use for new code."""
    pass
