from __future__ import annotations

from dataclasses import dataclass

from structure_comparer.model.mapping_action_models import ActionInfo, ActionType

from .extension_utils import ensure_extension_url_fix, is_extension_path
from .nodes import FieldNode

SKIP_ACTIONS: set[ActionType] = {
    ActionType.EMPTY,
    ActionType.NOT_USE,
    ActionType.COPY_TO,
}


@dataclass(slots=True)
class FieldTreeResult:
    root: FieldNode
    nodes_to_emit: list[FieldNode]
    field_source_support: dict[str, bool]


class FieldTreeBuilder:
    """Builds a FieldNode tree and prepares nodes for rule emission."""

    def __init__(
        self,
        *,
        mapping,
        actions: dict[str, ActionInfo],
        target_profile_key: str | None,
        source_profile_keys: list[str],
    ) -> None:
        self._mapping = mapping
        self._actions = actions
        self._target_profile_key = target_profile_key
        self._source_profile_keys = source_profile_keys

        self._root = FieldNode(segment="", path="")
        self._nodes_to_emit: list[FieldNode] = []
        self._blocked_prefixes: set[str] = set()
        self._field_source_support: dict[str, bool] = {}

    def build(self) -> FieldTreeResult:
        self._build_tree()
        self._annotate_tree(self._root)
        self._propagate_requires_source(self._root)
        self._apply_container_flags(self._root)
        self._collect_nodes(self._root)
        return FieldTreeResult(
            root=self._root,
            nodes_to_emit=self._nodes_to_emit,
            field_source_support=self._field_source_support,
        )

    # ------------------------------------------------------------------
    # Tree construction logic
    # ------------------------------------------------------------------
    def _build_tree(self) -> None:
        for field_name in self._mapping.fields.keys():
            if not self._should_include_field(field_name):
                continue
            self._ensure_node(field_name)

    def _should_include_field(self, path: str) -> bool:
        if self._is_blocked_path(path):
            return False

        if self._is_problematic_field(path):
            return False

        field = self._mapping.fields.get(path)
        supports_source = True
        if field is not None:
            supports_source = self._any_source_supports(field)
        self._field_source_support[path] = supports_source
        if field is None:
            return True

        if not self._target_profile_key:
            return True

        target_field = field.profiles.get(self._target_profile_key)
        if not self._profile_supports_field(target_field):
            self._blocked_prefixes.add(path)
            return False

        info = self._actions.get(path)
        if info and info.action == ActionType.COPY_FROM:
            return self._copy_from_source_supported(info)

        if self._action_needs_source_value(info) and not supports_source:
            self._blocked_prefixes.add(path)
            return False

        return True

    def _is_problematic_field(self, path: str) -> bool:
        relative = self._relative_path(path)
        if not relative:
            return False
        if relative.startswith("meta"):
            return not self._is_allowed_meta_field(path)
        if "[x]" in relative and ":" not in relative and not self._can_resolve_choice_field(path):
            return True
        return False

    def _is_allowed_meta_field(self, path: str) -> bool:
        info = self._actions.get(path)
        if info is None:
            return False
        if info.action == ActionType.FIXED:
            return True
        if info.action == ActionType.MANUAL and info.fixed_value:
            return True
        return False

    def _can_resolve_choice_field(self, path: str) -> bool:
        if not self._target_profile_key:
            return False
        field = self._mapping.fields.get(path)
        if not field:
            return False
        profile_field = field.profiles.get(self._target_profile_key)
        if not profile_field:
            return False
        data = getattr(profile_field, "_ProfileField__data", None)
        if not data:
            return False
        type_entries = getattr(data, "type", None)
        return bool(type_entries) and len(type_entries) == 1 and bool(type_entries[0].code)

    def _relative_path(self, path: str | None) -> str:
        if not path:
            return ""
        parts = path.split(".", 1)
        return parts[1] if len(parts) == 2 else ""

    def _is_blocked_path(self, path: str) -> bool:
        for blocked in self._blocked_prefixes:
            if path == blocked or path.startswith(f"{blocked}."):
                return True
        return False

    def _profile_supports_field(self, profile_field) -> bool:
        if profile_field is None:
            return False
        max_num = getattr(profile_field, "max_num", None)
        if max_num is None:
            return True
        return max_num != 0

    def _any_source_supports(self, field) -> bool:
        if not self._source_profile_keys:
            return True
        for key in self._source_profile_keys:
            profile_field = field.profiles.get(key)
            if self._profile_supports_field(profile_field):
                return True
        return False

    def _action_needs_source_value(self, info: ActionInfo | None) -> bool:
        if info is None:
            return True
        if info.action in SKIP_ACTIONS:
            return False
        if info.action == ActionType.USE_RECURSIVE:
            return False
        if info.action == ActionType.FIXED:
            return False
        if info.action == ActionType.MANUAL and info.fixed_value:
            return False
        if info.action == ActionType.COPY_FROM:
            return False
        return True

    def _action_requires_runtime_source(self, info: ActionInfo | None) -> bool:
        if info is None:
            return True
        if info.action == ActionType.USE_RECURSIVE:
            return False
        if info.action == ActionType.FIXED:
            return False
        if info.action == ActionType.MANUAL and info.fixed_value:
            return False
        return True

    def _copy_from_source_supported(self, info: ActionInfo) -> bool:
        other_path = info.other_value if isinstance(info.other_value, str) else None
        if not other_path:
            return False
        other_field = self._mapping.fields.get(other_path)
        if other_field is None:
            return False
        return self._any_source_supports(other_field)

    def _ensure_node(self, path: str) -> FieldNode:
        current = self._root
        segments: list[str] = []
        for segment in path.split("."):
            segments.append(segment)
            current_path = ".".join(segments)
            if segment not in current.children:
                current.children[segment] = FieldNode(segment=segment, path=current_path, parent=current)
            current = current.children[segment]
            interim_info = self._actions.get(current_path)
            if interim_info is not None:
                self._apply_action_info(current, interim_info, overwrite=False)

        info = self._actions.get(path)
        if info is not None:
            self._apply_action_info(current, info, overwrite=True)

        if (
            current.action == ActionType.COPY_FROM
            and is_extension_path(path)
            and not path.endswith(".url")
        ):
            ensure_extension_url_fix(
                node=current,
                mapping=self._mapping,
                target_profile_key=self._target_profile_key,
                source_profile_keys=self._source_profile_keys,
                ensure_node_callback=self._ensure_node,
            )

        return current

    def _apply_action_info(self, node: FieldNode, info: ActionInfo, *, overwrite: bool) -> None:
        if not overwrite and node.action is not None:
            return

        node.action = info.action

        needs_source = self._action_requires_runtime_source(info)
        if not needs_source:
            node.requires_source = False
        elif overwrite:
            node.requires_source = True

        other_path = info.other_value if isinstance(info.other_value, str) else None
        if overwrite or node.other_path is None:
            node.other_path = other_path

        fixed_val = info.fixed_value
        if fixed_val is not None and not isinstance(fixed_val, str):
            fixed_val = str(fixed_val)
        if overwrite or (node.fixed_value is None and fixed_val is not None):
            node.fixed_value = fixed_val

        remark = info.user_remark or info.system_remark
        if overwrite or (node.remark is None and remark):
            node.remark = remark

    def _annotate_tree(self, node: FieldNode) -> None:
        for child in node.children.values():
            self._annotate_tree(child)

        intent = self._determine_intent(node)
        node.intent = intent

        if intent not in {"copy", "copy_other", "copy_to"}:
            node.can_collapse = False
            node.collapse_kind = None
            return

        child_matches = True
        for child in node.children.values():
            if not child.can_collapse:
                child_matches = False
                break
            expected = (intent, node.other_path if intent in {"copy_other", "copy_to"} else None)
            if child.collapse_kind != expected:
                child_matches = False
                break

        node.can_collapse = child_matches
        node.collapse_kind = (intent, node.other_path if intent in {"copy_other", "copy_to"} else None)

    def _propagate_requires_source(self, node: FieldNode) -> bool:
        requires_source = node.requires_source
        for child in node.children.values():
            if self._propagate_requires_source(child):
                requires_source = True
        node.requires_source = requires_source
        return requires_source

    def _apply_container_flags(self, node: FieldNode) -> None:
        for child in node.children.values():
            self._apply_container_flags(child)

        if self._needs_container_node(node):
            node.force_container = True
            if all(not child.requires_source for child in node.children.values()):
                node.requires_source = False

    def _determine_intent(self, node: FieldNode) -> str:
        action = node.action
        if action is None and is_extension_path(node.path):
            return "skip"

        if action is None:
            return "copy"

        if action in SKIP_ACTIONS:
            return "skip"

        if action == ActionType.COPY_FROM:
            return "copy_other"

        if action == ActionType.COPY_TO:
            return "copy_to"

        if action == ActionType.FIXED:
            return "fixed"

        if action == ActionType.MANUAL:
            return "fixed" if node.fixed_value else "manual"

        return "copy"

    def _collect_nodes(self, node: FieldNode) -> None:
        slice_bases = self._collect_special_slice_bases(node)
        for child in sorted(node.children.values(), key=lambda item: item.path):
            if child.intent == "skip":
                self._collect_nodes(child)
                continue

            if ":" not in child.segment and child.intent in {"copy", "copy_other", "copy_to"}:
                base_name = child.segment
                if base_name in slice_bases:
                    continue

            if child.intent in {"copy", "copy_other", "copy_to"}:
                is_extension_slice = is_extension_path(child.path) and ":" in child.path.split(".")[-1]
                needs_container = self._needs_container_node(child)

                if (child.can_collapse and child.depth >= 2) or is_extension_slice:
                    self._nodes_to_emit.append(child)
                elif self._should_force_container(child):
                    child.force_container = True
                    self._nodes_to_emit.append(child)
                elif needs_container:
                    if child.depth >= 2:
                        self._nodes_to_emit.append(child)
                    else:
                        self._collect_nodes(child)
                else:
                    self._collect_nodes(child)
                continue

            if child.depth >= 2:
                self._nodes_to_emit.append(child)
            else:
                self._collect_nodes(child)

    def _should_force_container(self, node: FieldNode) -> bool:
        if node.depth < 2:
            return False
        if not node.children:
            return False
        if node.action == ActionType.USE_RECURSIVE:
            return True
        return self._is_repeating_field(node.path)

    def _collect_special_slice_bases(self, node: FieldNode) -> set[str]:
        bases: set[str] = set()
        for child in node.children.values():
            if ":" not in child.segment:
                continue
            if not self._needs_container_node(child):
                continue
            base = child.segment.split(":", 1)[0]
            bases.add(base)
        return bases

    def _needs_container_node(self, node: FieldNode) -> bool:
        if not node.children:
            return False
        if node.intent not in {"copy", "copy_other", "copy_to"}:
            return False
        for child in node.children.values():
            if child.intent not in {"copy", "copy_other", "copy_to"}:
                return True
        return False

    def _is_repeating_field(self, path: str | None) -> bool:
        if not path:
            return False
        field = self._mapping.fields.get(path)
        if not field:
            return False

        profile_candidates: list[str] = []
        if self._target_profile_key:
            profile_candidates.append(self._target_profile_key)
        profile_candidates.extend(self._source_profile_keys or [])

        profile_field = None
        for key in profile_candidates:
            if not key:
                continue
            candidate = field.profiles.get(key)
            if candidate is not None:
                profile_field = candidate
                break

        if profile_field is None:
            return False

        max_num = getattr(profile_field, "max_num", None)
        if max_num is None:
            return False

        try:
            return float(max_num) > 1
        except (TypeError, ValueError):
            return False
