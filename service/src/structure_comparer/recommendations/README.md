# Recommendations Module

This module contains the refactored recommendation engine system for generating field mapping recommendations.

## Architecture

The recommendation system has been split into specialized classes for better maintainability and clarity:

### Core Components

- **`recommendation_engine.py`** - Main orchestrator that coordinates all recommenders
- **`field_utils.py`** - Utility functions for field analysis (e.g., cardinality checks)

### Recommender Classes

Each recommender is responsible for a specific type of recommendation:

1. **`compatible_recommender.py`** - `CompatibleRecommender`
   - Generates `USE` and `USE_RECURSIVE` recommendations for compatible fields
   - Skips fields with 0..0 cardinality in all source profiles

2. **`inherited_recommender.py`** - `InheritedRecommender`
   - Base class for computing inherited recommendations from parent fields
   - Implements the generic inheritance logic used by other recommenders
   - Skips fields with 0..0 cardinality in all source profiles

3. **`copy_recommender.py`** - `CopyRecommender`
   - Generates inherited `COPY_FROM`/`COPY_TO` recommendations
   - Includes conflict detection for target fields
   - Handles fixed value conflicts

4. **`use_recursive_recommender.py`** - `UseRecursiveRecommender`
   - Generates `USE` recommendations for children of `USE_RECURSIVE` fields
   - Delegates to `InheritedRecommender`

5. **`use_not_use_recommender.py`** - `UseNotUseRecommender`
   - Generates inherited `USE`/`NOT_USE` recommendations from parent fields
   - Delegates to `InheritedRecommender`

6. **`zero_cardinality_recommender.py`** - `ZeroCardinalityRecommender`
   - Generates `NOT_USE` recommendations for fields with 0..0 cardinality in ALL source profiles
   - This is the ONLY recommendation type generated for such fields

## Key Behavior

### Zero Cardinality Handling

Fields with cardinality `0..0` in **all** source profiles receive special treatment:

- ✅ Generate `NOT_USE` recommendation (via `ZeroCardinalityRecommender`)
- ❌ Skip all other recommendation types (compatible, inherited, etc.)
- This ensures only one clear recommendation for unusable fields

### Recommendation Priority

Recommendations are computed in this order:

1. Compatible field recommendations (USE, USE_RECURSIVE)
2. Inherited copy recommendations (COPY_FROM, COPY_TO)
3. USE_RECURSIVE inheritance
4. USE/NOT_USE inheritance
5. Zero cardinality NOT_USE recommendations

Duplicates are removed, keeping only the first occurrence of each action type per field.

## Usage

```python
from structure_comparer.recommendations import RecommendationEngine

engine = RecommendationEngine(mapping, manual_entries)
recommendations = engine.compute_all_recommendations()
```

The recommendations are returned as a dictionary mapping field names to lists of `ActionInfo` objects.

## Backward Compatibility

The old `recommendation_engine.py` module at the parent level still exists and re-exports `RecommendationEngine` for backward compatibility. All new code should import from the `recommendations` package.
