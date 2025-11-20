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


def compute_mapping_actions(mapping, manual_entries: Optional[Mapping[str, dict]] = None) -> Dict[str, ActionInfo]:
    """Compute effective :class:`ActionInfo` for each field in *mapping*.

    The function favours manual decisions over inherited ones and falls back
    to system defaults when no information is available.
    """

    fields = getattr(mapping, "fields", {}) or {}
    manual_map = _normalise_manual_entries(manual_entries)
    manual_map_for_compute = _augment_copy_links(manual_map)

    # Process parents before children so inheritance works deterministically.
    ordered_field_names = sorted(fields.keys(), key=_field_depth)
    result: Dict[str, ActionInfo] = {}

    for field_name in ordered_field_names:
        manual_entry = manual_map_for_compute.get(field_name)
        field = fields.get(field_name)
        if manual_entry is not None:
            info = _action_from_manual(field_name, manual_entry)
        else:
            info = _inherit_or_default(field_name, field, result)

        result[field_name] = info

    return result


def _normalise_manual_entries(manual_entries: Optional[Mapping[str, dict]]) -> Dict[str, dict]:
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


def _action_from_manual(field_name: str, manual_entry: Mapping[str, object]) -> ActionInfo:
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
) -> ActionInfo:
    parent_name = _parent_name(field_name)
    if parent_name:
        parent_info = result.get(parent_name)
        if parent_info and parent_info.action in _INHERITABLE_ACTIONS:
            return ActionInfo(
                action=parent_info.action,
                source=ActionSource.INHERITED,
                inherited_from=parent_name,
                auto_generated=True,
                system_remark=f"Inherited from {parent_name}",
                fixed_value=parent_info.fixed_value,
                other_value=parent_info.other_value,
            )

    classification = getattr(field, "classification", "unknown") if field is not None else "unknown"

    if str(classification).lower() == "compatible":
        return ActionInfo(
            action=ActionType.USE,
            source=ActionSource.SYSTEM_DEFAULT,
            auto_generated=True,
            system_remark="Default action applied",
        )

    return ActionInfo(
        action=ActionType.OTHER,
        source=ActionSource.SYSTEM_DEFAULT,
        auto_generated=True,
        system_remark="No default action available",
    )


def _parse_action(value: object) -> ActionType:
    if isinstance(value, ActionType):
        return value
    if isinstance(value, str):
        try:
            return ActionType(value)
        except ValueError:
            return ActionType.OTHER
    return ActionType.OTHER


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

    augmented: Dict[str, dict] = {name: dict(entry) for name, entry in manual_map.items()}

    for name, entry in manual_map.items():
        action = _parse_action(entry.get("action"))
        other = entry.get("other")
        if not other:
            continue

        if action == ActionType.COPY_FROM:
            augmented.setdefault(other, {"action": ActionType.COPY_TO.value, "other": name, "_derived": True})
        elif action == ActionType.COPY_TO:
            augmented.setdefault(other, {"action": ActionType.COPY_FROM.value, "other": name, "_derived": True})

    return augmented
