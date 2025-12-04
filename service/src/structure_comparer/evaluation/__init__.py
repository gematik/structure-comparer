"""Evaluation module for mapping and target creation status analysis.

=== IMPLEMENTATION STATUS ===
Phase 3, Step 3.1 & 3.2: Target Creation Evaluation ✅
Updated: 2025-12-03 - Added Target Creation evaluation exports
"""

from .status_aggregator import StatusAggregator
from .status_propagator import StatusPropagator
from .target_creation_evaluation import (
    TargetCreationStatusAggregator,
    compute_target_creation_actions,
    evaluate_target_creation,
    evaluate_target_creation_field,
)

__all__ = [
    "StatusAggregator",
    "StatusPropagator",
    "TargetCreationStatusAggregator",
    "compute_target_creation_actions",
    "evaluate_target_creation",
    "evaluate_target_creation_field",
]
