"""Experimental mapping actions engine (Step 3).

The function provided in this module is developed TDD-first alongside
`test_mapping_actions_engine.py`. It is intentionally isolated from the
existing production logic until the rewrite reaches parity.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .field_utils import field_depth, parent_name
from .model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
)
from .recommendation_engine import RecommendationEngine

_INHERITABLE_ACTIONS = {
    ActionType.NOT_USE,
    ActionType.EMPTY,
    ActionType.USE_RECURSIVE,
    ActionType.COPY_FROM,
    ActionType.COPY_TO,
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
            payload.pop("auto_generated", None)
            payload.pop("inherited_from", None)
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
    else:
        source = ActionSource.MANUAL
        auto_generated = False
        inherited_from = None

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
            # For copy_from/copy_to: DON'T inherit as active action anymore
            # These will be handled as recommendations instead
            is_copy_action = parent_info.action in {
                ActionType.COPY_FROM,
                ActionType.COPY_TO,
            }
            
            if is_copy_action:
                # Skip inheritance for copy actions, fall through to default
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

    # Check for patternCoding.system in target field
    pattern_system = _get_pattern_coding_system(field, target_key, all_fields)
    if pattern_system:
        return ActionInfo(
            action=ActionType.FIXED,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark="Auto-detected from patternCoding.system in target profile",
            fixed_value=pattern_system,
        )

    classification = (
        getattr(field, "classification", "unknown") if field is not None else "unknown"
    )

    # For compatible fields: Do NOT set an active action anymore
    # Instead, return None action (will be converted to recommendation later)
    # This ensures compatible fields don't automatically get "solved" status
    if str(classification).lower() == "compatible":
        return ActionInfo(
            action=None,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark="Default recommendation: USE (not yet applied)",
        )

    # No default action available for warning/incompatible fields
    # User must explicitly select an action
    return ActionInfo(
        action=None,
        source=ActionSource.SYSTEM_DEFAULT,
        auto_generated=True,
        system_remark="No action selected - user decision required",
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
