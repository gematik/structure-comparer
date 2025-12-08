"""Experimental mapping actions engine (Step 3).

The function provided in this module is developed TDD-first alongside
`test_mapping_actions_engine.py`. It is intentionally isolated from the
existing production logic until the rewrite reaches parity.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .action import Action
from .field_hierarchy import field_depth, parent_name
from .field_hierarchy.field_hierarchy_analyzer import all_descendants_compatible_or_solved
from .field_hierarchy.field_navigator import FieldHierarchyNavigator
from .fixed_value_extractor import FixedValueExtractor
from .model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
    EvaluationResult,
)
from .recommendation_engine import RecommendationEngine

_INHERITABLE_ACTIONS = {
    # ActionType.NOT_USE,  # Removed: Now handled as recommendation only
    ActionType.EMPTY,
    ActionType.USE_RECURSIVE,
    ActionType.COPY_FROM,
    ActionType.COPY_TO,
    ActionType.EXTENSION,  # Extension actions should be inherited to child fields
}


def compute_mapping_actions(
    mapping, manual_entries: Optional[Mapping[str, dict]] = None
) -> Dict[str, ActionInfo]:
    """Compute effective :class:`ActionInfo` for each field in *mapping*.

    The function favours manual decisions over inherited ones and falls back
    to system defaults when no information is available.
    """

    fields = getattr(mapping, "fields", {}) or {}
    manual_map = _normalise_manual_entries(manual_entries)
    manual_map_for_compute = _augment_copy_links(manual_map)

    # Get target profile key for pattern detection
    target = getattr(mapping, "target", None)
    target_key = target.key if target else None

    # Process parents before children so inheritance works deterministically.
    ordered_field_names = sorted(fields.keys(), key=field_depth)
    result: Dict[str, ActionInfo] = {}

    for field_name in ordered_field_names:
        manual_entry = manual_map_for_compute.get(field_name)
        field = fields.get(field_name)
        if manual_entry is not None:
            info = _action_from_manual(field_name, manual_entry)
        else:
            info = _inherit_or_default(field_name, field, result, fields, target_key)

        result[field_name] = info

    # Propagate NOT_USE from parent fields to direct children
    _propagate_not_use_to_direct_children(mapping, result)

    return result


def compute_recommendations(
    mapping, manual_entries: Optional[Mapping[str, dict]] = None
) -> Dict[str, list[ActionInfo]]:
    """Compute recommendations for fields that have no active action.
    
    Recommendations are suggested actions that do NOT influence mapping status.
    They must be explicitly applied by the user to become active actions.
    
    Returns:
        Dict mapping field names to lists of ActionInfo objects representing recommendations.
        Each field can have 0..n recommendations.
        
        Includes:
        1. Compatible fields -> USE recommendation
        2. Inherited copy_from/copy_to -> inherited recommendation with adjusted other_value
    """
    engine = RecommendationEngine(mapping, manual_entries)
    return engine.compute_all_recommendations()


def _normalise_manual_entries(
    manual_entries: Optional[Mapping[str, dict]],
) -> Dict[str, dict]:
    if not manual_entries:
        return {}

    # If we are given a Pydantic model or similar with a ``fields`` attribute,
    # convert it into a name -> dict representation.
    if not isinstance(manual_entries, Mapping) and hasattr(manual_entries, "fields"):
        field_entries = getattr(manual_entries, "fields", [])
        normalised: Dict[str, dict] = {}
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
            _ensure_other_key(payload)
            # Allow explicit 'use' actions to be treated as manual decisions
            # This enables users to resolve warnings by explicitly setting an action
            if payload.get("auto_generated"):
                continue
            # Keep auto_generated and inherited_from in the payload
            # They are used to determine the action source
            normalised[name] = payload
        return normalised

    cleaned: Dict[str, dict] = {}
    for name, data in manual_entries.items():
        payload = dict(data) if isinstance(data, Mapping) else data
        _ensure_other_key(payload)
        # Allow explicit 'use' actions to be treated as manual decisions
        # This enables users to resolve warnings by explicitly setting an action
        if payload.get("auto_generated"):
            continue
        payload.pop("auto_generated", None)
        payload.pop("inherited_from", None)
        cleaned[name] = payload
    return cleaned


def _action_from_manual(
    field_name: str, manual_entry: Mapping[str, object]
) -> ActionInfo:
    entry = dict(manual_entry)
    entry.pop("_derived", None)
    action_value = entry.get("action")
    action = _parse_action(action_value)

    inherited_from = entry.get("inherited_from")
    auto_generated = bool(entry.get("auto_generated"))

    if auto_generated and inherited_from:
        source = ActionSource.INHERITED
    elif inherited_from:
        # Manually applied but inherited (e.g., user clicked "apply to children")
        source = ActionSource.INHERITED
    else:
        source = ActionSource.MANUAL

    info = ActionInfo(
        action=action,
        source=source,
        inherited_from=inherited_from,
        auto_generated=auto_generated,
        user_remark=entry.get("remark"),
        fixed_value=entry.get("fixed"),
        other_value=entry.get("other"),
        raw_manual_entry=entry,
    )

    return info


def _propagate_not_use_to_direct_children(
    mapping, action_info_map: Dict[str, ActionInfo]
) -> None:
    """Automatically propagate NOT_USE action from parent to direct children.
    
    When a field has NOT_USE with source=MANUAL, all its direct children
    without manual actions receive NOT_USE with source=INHERITED.
    
    Args:
        mapping: The mapping object containing fields
        action_info_map: Dictionary mapping field names to ActionInfo objects.
                         This is modified in-place.
    """
    fields = getattr(mapping, "fields", {}) or {}
    if not fields:
        return
    
    navigator = FieldHierarchyNavigator(fields)
    
    # Collect all fields with manual NOT_USE
    fields_with_manual_not_use = [
        (field_name, action_info)
        for field_name, action_info in action_info_map.items()
        if action_info.action == ActionType.NOT_USE
        and action_info.source == ActionSource.MANUAL
    ]
    
    # For each parent with manual NOT_USE
    for parent_field_name, parent_action in fields_with_manual_not_use:
        direct_children = navigator.get_direct_children(parent_field_name)
        
        for child_field_name in direct_children:
            # Check if child already has a manual action
            child_action = action_info_map.get(child_field_name)
            if child_action and child_action.source == ActionSource.MANUAL:
                # Don't override manual actions
                continue
            
            # Set NOT_USE on child
            action_info_map[child_field_name] = ActionInfo(
                action=ActionType.NOT_USE,
                source=ActionSource.INHERITED,
                inherited_from=parent_field_name,
                system_remark=f"Automatically inherited NOT_USE from parent field {parent_field_name}",
                auto_generated=True
            )


def _inherit_or_default(
    field_name: str,
    field,
    result: Dict[str, ActionInfo],
    all_fields: Dict[str, object],
    target_key: Optional[str] = None,
) -> ActionInfo:
    field_parent_name = parent_name(field_name)
    if field_parent_name:
        parent_info = result.get(field_parent_name)
        if parent_info and parent_info.action in _INHERITABLE_ACTIONS:
            # For copy_from/copy_to/extension: DON'T inherit as active action anymore
            # These will be handled as recommendations instead
            is_copy_action = parent_info.action in {
                ActionType.COPY_FROM,
                ActionType.COPY_TO,
                ActionType.EXTENSION,  # Extension actions also handled as recommendations
            }
            
            if is_copy_action:
                # Skip inheritance for copy and extension actions, fall through to default
                # These fields will get recommendations instead of active inherited actions
                pass
            else:
                # Other inheritable actions (NOT_USE, EMPTY, USE_RECURSIVE)
                # Continue with existing inheritance logic
                return ActionInfo(
                    action=parent_info.action,
                    source=ActionSource.INHERITED,
                    inherited_from=field_parent_name,
                    auto_generated=True,
                    system_remark=f"Inherited from {field_parent_name}",
                    fixed_value=parent_info.fixed_value,
                    other_value=parent_info.other_value,
                )

    # Check for any fixed value in target field
    fixed_value = _get_fixed_value_from_field(field, target_key, all_fields)
    if fixed_value is not None:
        return ActionInfo(
            action=ActionType.FIXED,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark="Auto-detected fixed value from target profile",
            fixed_value=fixed_value,
        )

    classification = (
        getattr(field, "classification", "unknown") if field is not None else "unknown"
    )

    # For compatible fields: Do NOT set an active action anymore
    # Instead, return None action (will be converted to recommendation later)
    # This ensures compatible fields don't automatically get "solved" status
    if str(classification).lower() == "compatible":
        # Check if USE action is allowed for this field
        actions_allowed = getattr(field, "actions_allowed", None)
        if actions_allowed is not None and ActionType.USE not in actions_allowed:
            # USE is not allowed - show user decision required message
            return ActionInfo(
                action=None,
                source=ActionSource.SYSTEM_DEFAULT,
                auto_generated=True,
                system_remark=None,
            )
        
        # USE is allowed or no restrictions - show recommendation
        return ActionInfo(
            action=None,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark=None,
        )

    # No default action available for warning/incompatible fields
    # User must explicitly select an action
    return ActionInfo(
        action=None,
        source=ActionSource.SYSTEM_DEFAULT,
        auto_generated=True,
        system_remark=None,
    )


def _parse_action(value: object) -> ActionType | None:
    """Parse action value from manual entries or other sources.

    Returns:
        - ActionType: if value is a valid action type
        - None: if value is None, invalid, or cannot be parsed
    """
    if value is None:
        return None
    if isinstance(value, ActionType):
        return value
    # IMPORTANT: Also handle legacy Action enum (from action.py)
    # This ensures that applying a USE_RECURSIVE recommendation (which writes Action.USE_RECURSIVE)
    # behaves exactly like manually selecting USE_RECURSIVE.
    if isinstance(value, Action):
        try:
            return ActionType(value.value)
        except ValueError:
            # Invalid action value -> treat as "no action selected"
            return None
    if isinstance(value, str):
        try:
            return ActionType(value)
        except ValueError:
            # Invalid action string -> treat as "no action selected"
            return None
    return None


# Legacy aliases for backwards compatibility
# Use field_utils.field_depth and field_utils.parent_name instead
def _field_depth(name: str) -> int:
    return field_depth(name)


def _parent_name(name: str) -> Optional[str]:
    return parent_name(name)


def _is_default_use(value: object) -> bool:
    if isinstance(value, ActionType):
        return value == ActionType.USE
    if isinstance(value, str):
        return value == ActionType.USE.value
    return False


def _ensure_other_key(payload: dict) -> None:
    if "other" in payload and payload["other"]:
        return
    extra = payload.pop("extra", None)
    if extra:
        payload["other"] = extra


def _augment_copy_links(manual_map: Dict[str, dict]) -> Dict[str, dict]:
    if not manual_map:
        return {}

    augmented: Dict[str, dict] = {
        name: dict(entry) for name, entry in manual_map.items()
    }

    for name, entry in manual_map.items():
        action = _parse_action(entry.get("action"))
        other = entry.get("other")
        if not other:
            continue

        if action == ActionType.COPY_FROM:
            augmented.setdefault(
                other,
                {"action": ActionType.COPY_TO.value, "other": name, "_derived": True},
            )
        elif action == ActionType.COPY_TO:
            augmented.setdefault(
                other,
                {"action": ActionType.COPY_FROM.value, "other": name, "_derived": True},
            )

    return augmented


def _get_pattern_coding_system(
    field, target_key: Optional[str], all_fields: Dict[str, object]
) -> Optional[str]:
    """Extract pattern_coding_system from target field's profile, if available.

    For a field like 'Medication.code.coding:atc-de.system', check if the parent
    field 'Medication.code.coding:atc-de' has a patternCoding with a system value.

    Note: This function should ONLY return a value for .system fields, not for
    the parent Coding field itself (which has the patternCoding).
    """
    if field is None or target_key is None:
        return None

    # Only apply to .system fields - if this is a .system field, check the parent
    field_name = getattr(field, "name", None)
    if field_name and field_name.endswith(".system"):
        # Get the parent field name (remove ".system")
        parent_name = field_name.rsplit(".", 1)[0]
        parent_field = all_fields.get(parent_name)

        if parent_field:
            parent_profiles = getattr(parent_field, "profiles", {})
            parent_target_field = parent_profiles.get(target_key)
            if parent_target_field:
                parent_pattern_system = getattr(
                    parent_target_field, "pattern_coding_system", None
                )
                if parent_pattern_system:
                    return parent_pattern_system

    return None


def _get_fixed_value_from_field(
    field, target_key: Optional[str], all_fields: Dict[str, object]
) -> Optional[Any]:
    """Extract any fixed value from target field's profile.
    
    This function checks for:
    1. Direct fixed values (fixedUri, fixedString, fixedCode, etc.)
    2. Pattern coding system for .system fields
    
    Args:
        field: The field to check
        target_key: The target profile key
        all_fields: All fields in the mapping
        
    Returns:
        The fixed value if found, None otherwise
    """
    if field is None or target_key is None:
        return None
    
    # Get the target profile field
    profiles = getattr(field, "profiles", {})
    target_field = profiles.get(target_key)
    
    if target_field is None:
        return None
    
    # First check for direct fixed value
    fixed_value = getattr(target_field, "fixed_value", None)
    if fixed_value is not None:
        return fixed_value
    
    # For .system fields, check parent's patternCoding
    field_name = getattr(field, "name", None)
    if field_name and field_name.endswith(".system"):
        pattern_system = _get_pattern_coding_system(field, target_key, all_fields)
        if pattern_system is not None:
            return pattern_system
    
    return None


def adjust_use_recursive_actions_allowed(
    mapping, evaluation_map: Dict[str, EvaluationResult],
    action_info_map: Dict[str, ActionInfo] = None
) -> None:
    """Adjust actions_allowed for all fields regarding use_recursive.
    
    This function applies evaluation-aware logic to determine whether
    use_recursive should be in actions_allowed:
    - use_recursive is allowed when the field has descendants AND
      all descendants WITHOUT manual actions are either compatible or solved.
    - Otherwise, use_recursive is removed from actions_allowed.
    
    This is a second pass after the baseline actions_allowed has been set
    by fill_allowed_actions(), enriching it with knowledge from evaluation
    and manual actions.
    
    Args:
        mapping: The mapping object with fields
        evaluation_map: Dictionary mapping field names to EvaluationResult
        action_info_map: Optional dictionary mapping field names to ActionInfo objects.
                         If provided, only descendants WITHOUT manual actions are considered.
    """
    fields = getattr(mapping, "fields", {})
    if not fields:
        return
    
    navigator = FieldHierarchyNavigator(fields)
    
    for field_name, field in fields.items():
        # Check if field has descendants
        descendants = navigator.get_all_descendants(field_name)
        
        if not descendants:
            # Leaf field: remove use_recursive if present
            if Action.USE_RECURSIVE in field.actions_allowed:
                field.actions_allowed.remove(Action.USE_RECURSIVE)
        else:
            # Field has descendants: check if all (without manual actions) are compatible or solved
            all_ok = all_descendants_compatible_or_solved(
                field_name, fields, evaluation_map, action_info_map
            )
            
            if all_ok:
                # Ensure use_recursive is in actions_allowed (if not already)
                if Action.USE_RECURSIVE not in field.actions_allowed:
                    field.actions_allowed.append(Action.USE_RECURSIVE)
            else:
                # Not all descendants are compatible/solved: remove use_recursive
                if Action.USE_RECURSIVE in field.actions_allowed:
                    field.actions_allowed.remove(Action.USE_RECURSIVE)

