"""Experimental mapping actions engine (Step 3).

The function provided in this module is developed TDD-first alongside
`test_mapping_actions_engine.py`. It is intentionally isolated from the
existing production logic until the rewrite reaches parity.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
)

_INHERITABLE_ACTIONS = {
    ActionType.NOT_USE,
    ActionType.EMPTY,
    ActionType.EXTENSION,
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
    ordered_field_names = sorted(fields.keys(), key=_field_depth)
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
    parent_name = _parent_name(field_name)
    if parent_name:
        parent_info = result.get(parent_name)
        if parent_info and parent_info.action in _INHERITABLE_ACTIONS:
            # Adjust other_value for child fields when inheriting copy_from/copy_to
            inherited_other_value = parent_info.other_value
            if inherited_other_value and parent_info.action in {
                ActionType.COPY_FROM,
                ActionType.COPY_TO,
            }:
                # Extract the child suffix from the current field
                child_suffix = field_name[
                    len(parent_name) :
                ]  # e.g., ".system" or ".code"

                # Don't inherit for polymorphic type choices (e.g., :valueBoolean)
                # These are concrete type implementations, not structural children
                if child_suffix.startswith(":value"):
                    # Fall through to default logic
                    pass
                else:
                    # Append the same suffix to the parent's other_value
                    candidate_other_value = inherited_other_value + child_suffix

                    # Check if target field exists
                    target_exists = candidate_other_value in all_fields

                    # If direct target doesn't exist and parent is polymorphic value[x],
                    # try to find matching type choice
                    if not target_exists and ".value[x]" in inherited_other_value:
                        # Look for type choices (e.g., :valueCoding, :valueString)
                        type_choices = [
                            f
                            for f in all_fields.keys()
                            if f.startswith(inherited_other_value + ":")
                            and f.count(":") == inherited_other_value.count(":") + 1
                        ]

                        if type_choices:
                            # Try each type choice with the child suffix
                            for type_choice in type_choices:
                                alternative_target = type_choice + child_suffix
                                if alternative_target in all_fields:
                                    candidate_other_value = alternative_target
                                    target_exists = True
                                    break

                    # Validate that the target field actually exists
                    if target_exists:
                        inherited_other_value = candidate_other_value
                    else:
                        # Target field doesn't exist, don't inherit the action
                        # Fall through to default logic below
                        inherited_other_value = None

            is_copy_action = parent_info.action in {
                ActionType.COPY_FROM,
                ActionType.COPY_TO,
            }
            if inherited_other_value is not None or not is_copy_action:
                return ActionInfo(
                    action=parent_info.action,
                    source=ActionSource.INHERITED,
                    inherited_from=parent_name,
                    auto_generated=True,
                    system_remark=f"Inherited from {parent_name}",
                    fixed_value=parent_info.fixed_value,
                    other_value=inherited_other_value,
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

    if str(classification).lower() == "compatible":
        return ActionInfo(
            action=ActionType.USE,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark="Default action applied",
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


def _field_depth(name: str) -> int:
    return name.count(".") + name.count(":")


def _parent_name(name: str) -> Optional[str]:
    dot_index = name.rfind(".")
    colon_index = name.rfind(":")
    split_index = max(dot_index, colon_index)
    if split_index == -1:
        return None
    return name[:split_index]


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
