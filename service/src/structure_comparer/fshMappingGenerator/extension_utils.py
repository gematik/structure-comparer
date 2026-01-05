from __future__ import annotations

from structure_comparer.model.mapping_action_models import ActionInfo, ActionType

from .nodes import FieldNode


def is_extension_path(path: str | None) -> bool:
    if not path:
        return False
    last_segment = path.split(".")[-1]
    base_name = last_segment.split(":")[0]
    return base_name in {"extension", "modifierExtension"}


def get_extension_url(mapping, path: str, profile_keys: str | list[str] | None = None):
    if not path:
        return None

    field = mapping.fields.get(path)
    if not field:
        url_path = f"{path}.url"
        field = mapping.fields.get(url_path)
        if not field:
            return None

    if profile_keys is None:
        keys = [p.key for p in mapping.sources or []]
    elif isinstance(profile_keys, str):
        keys = [profile_keys]
    else:
        keys = profile_keys

    for alias in keys:
        profile_field = field.profiles.get(alias)
        if profile_field:
            data = getattr(profile_field, "_ProfileField__data", None)
            if data and data.type:
                for entry in data.type:
                    if entry.code == "Extension" and entry.profile:
                        return entry.profile[0]

        # Check for fixedUri on explicit url child if profile data not informative
        url_path = f"{path}.url" if not path.endswith(".url") else path
        url_field = mapping.fields.get(url_path)
        if url_field:
            url_profile_field = url_field.profiles.get(alias)
            if url_profile_field:
                url_data = getattr(url_profile_field, "_ProfileField__data", None)
                fixed_uri = getattr(url_data, "fixedUri", None) if url_data else None
                if fixed_uri:
                    return fixed_uri
    return None


def ensure_extension_url_fix(
    node: FieldNode,
    mapping,
    target_profile_key: str | None,
    source_profile_keys: list[str],
    ensure_node_callback,
) -> None:
    target_url = get_extension_url(mapping, node.path, target_profile_key)
    source_url = get_extension_url(mapping, node.other_path, source_profile_keys)
    if not target_url or not source_url or target_url == source_url:
        return

    url_node = ensure_node_callback(f"{node.path}.url")
    url_node.action = ActionType.FIXED
    url_node.fixed_value = target_url
    if not url_node.remark:
        url_node.remark = "Set canonical URL for extension"


def find_skipped_slices(
    node: FieldNode,
    actions: dict[str, ActionInfo],
    mapping,
    target_profile_key: str | None,
    skip_actions: set[ActionType],
) -> list[str]:
    skipped_urls: list[str] = []
    prefixes = [node.path + ":", node.path + ".extension:"]

    for path, info in actions.items():
        if not any(path.startswith(prefix) for prefix in prefixes):
            continue

        should_skip = False
        if info.action in skip_actions:
            should_skip = True
        elif info.action in {ActionType.COPY_VALUE_TO, ActionType.COPY_NODE_TO, ActionType.MANUAL, ActionType.USE}:
            should_skip = True
        elif is_extension_path(path):
            # Skip explicitly mapped slices so the generic extension copy rule
            # does not pull them in again.
            last_segment = path.split(".")[-1]
            if ":" in last_segment:
                should_skip = True
        else:
            field = mapping.fields.get(path)
            if field:
                target_field = field.profiles.get(target_profile_key) if target_profile_key else None
                if target_field and getattr(target_field, "max_num", 1) == 0:
                    should_skip = True

        if should_skip:
            slice_name = _slice_name(path)

            # Prefer canonical URLs but also include the slice name so source-side
            # conditions can exclude the original slice label when the target URL
            # is changed (e.g., Kennzeichen -> indicator).
            url_candidates = [
                get_extension_url(mapping, path),
                _action_fixed_url(actions, path),
                slice_name,
            ]

            for url in url_candidates:
                if url:
                    skipped_urls.append(url)

    return list(set(skipped_urls))


def _action_fixed_url(actions: dict[str, ActionInfo], path: str) -> str | None:
    """Fallback to action-based fixed url hints when profile data is missing."""

    action = actions.get(path)
    if action and action.fixed_value:
        return action.fixed_value

    url_path = f"{path}.url" if not path.endswith(".url") else path
    url_action = actions.get(url_path)
    if url_action and url_action.fixed_value:
        return url_action.fixed_value

    return None


def _slice_name(path: str) -> str | None:
    if not path:
        return None
    last_segment = path.split(".")[-1]
    if ":" in last_segment:
        return last_segment.split(":", 1)[1]
    return None
