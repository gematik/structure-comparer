"""StructureMap export helpers.

The service stores mapping instructions on a field-by-field basis.  This module
turns those instructions into a ``StructureMap`` JSON representation that can be
served directly or converted to FSH later on.  The JSON format is easier to
validate and aligns with the FastAPI download endpoint that expects textual
content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import TYPE_CHECKING

from structure_comparer.model.mapping_action_models import ActionInfo, ActionType

if TYPE_CHECKING:  # pragma: no cover - only used for type checking
    from structure_comparer.data.mapping import Mapping


@dataclass(slots=True)
class _FieldNode:
    """Helper tree node describing a mapping field."""

    segment: str
    path: str
    parent: _FieldNode | None = None
    action: ActionType | None = None
    other_path: str | None = None
    fixed_value: str | None = None
    remark: str | None = None
    intent: str = "copy"  # copy | copy_other | fixed | manual | skip
    collapse_kind: tuple[str, str | None] | None = None
    can_collapse: bool = False
    children: dict[str, "_FieldNode"] = field(default_factory=dict)

    @property
    def depth(self) -> int:
        return 0 if not self.path else len(self.path.split("."))


_SKIP_ACTIONS: set[ActionType] = {
    ActionType.EMPTY,
    ActionType.NOT_USE,
    ActionType.COPY_TO,
}


def build_structuremap_fsh(
    mapping: "Mapping",
    actions: dict[str, ActionInfo],
    *,
    source_alias: str,
    target_alias: str,
    ruleset_name: str,
) -> str:
    """Build a StructureMap JSON string based on mapping actions."""

    builder = _StructureMapBuilder(
        mapping=mapping,
        actions=actions,
        source_alias=source_alias,
        target_alias=target_alias,
        ruleset_name=ruleset_name,
    )
    structure_map = builder.build()
    return json.dumps(structure_map, indent=2, ensure_ascii=False)


class _StructureMapBuilder:
    """Internal helper that assembles a StructureMap dict."""

    def __init__(
        self,
        *,
        mapping: "Mapping",
        actions: dict[str, ActionInfo],
        source_alias: str,
        target_alias: str,
        ruleset_name: str,
    ) -> None:
        self._mapping = mapping
        self._actions = actions
        self._source_alias = source_alias or "source"
        self._target_alias = target_alias or "target"
        self._ruleset_name = ruleset_name or "structuremap"

        self._root = _FieldNode(segment="", path="")
        self._nodes_to_emit: list[_FieldNode] = []
        self._source_aliases = self._compute_source_aliases()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self) -> dict:
        self._build_tree()
        self._annotate_tree(self._root)
        self._collect_nodes(self._root)

        if not self._nodes_to_emit:
            first_path = self._first_field_path()
            if first_path:
                fallback_node = _FieldNode(segment=first_path.split(".")[-1], path=first_path)
                fallback_node.intent = "copy"
                fallback_node.can_collapse = True
                fallback_node.collapse_kind = ("copy", None)
                self._nodes_to_emit.append(fallback_node)

        rules = [self._build_rule(node) for node in self._nodes_to_emit]
        rules = [rule for rule in rules if rule is not None]

        return {
            "resourceType": "StructureMap",
            "id": self._slug(self._ruleset_name, suffix=self._stable_id(self._ruleset_name)),
            "url": f"{self._mapping.target.url}/StructureMap/{self._ruleset_name}",
            "name": self._ruleset_name,
            "status": self._mapping.status or "draft",
            "version": self._mapping.version,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "description": f"Auto-generated StructureMap for {self._mapping.name}",
            "structure": self._build_structure_section(),
            "group": [
                {
                    "name": self._ruleset_name,
                    "typeMode": "none",
                    "documentation": f"Mapping generated for {self._mapping.name}",
                    "input": self._build_inputs_section(),
                    "rule": rules,
                }
            ],
        }

    # ------------------------------------------------------------------
    # Tree preparation
    # ------------------------------------------------------------------
    def _build_tree(self) -> None:
        for field_name in self._mapping.fields.keys():
            self._ensure_node(field_name)

    def _ensure_node(self, path: str) -> _FieldNode:
        current = self._root
        segments: list[str] = []
        for segment in path.split("."):
            segments.append(segment)
            current_path = ".".join(segments)
            if segment not in current.children:
                current.children[segment] = _FieldNode(segment=segment, path=current_path, parent=current)
            current = current.children[segment]

        info = self._actions.get(path)
        if info is not None:
            current.action = info.action
            current.other_path = info.other_value if isinstance(info.other_value, str) else None
            fixed_val = info.fixed_value
            if fixed_val is not None and not isinstance(fixed_val, str):
                fixed_val = str(fixed_val)
            current.fixed_value = fixed_val
            current.remark = info.user_remark or info.system_remark

        return current

    def _annotate_tree(self, node: _FieldNode) -> None:
        for child in node.children.values():
            self._annotate_tree(child)

        intent = self._determine_intent(node)
        node.intent = intent

        if intent not in {"copy", "copy_other"}:
            node.can_collapse = False
            node.collapse_kind = None
            return

        child_matches = True
        for child in node.children.values():
            if not child.can_collapse:
                child_matches = False
                break
            if child.collapse_kind != (intent, node.other_path if intent == "copy_other" else None):
                child_matches = False
                break

        node.can_collapse = child_matches
        node.collapse_kind = (intent, node.other_path if intent == "copy_other" else None)

    def _determine_intent(self, node: _FieldNode) -> str:
        action = node.action
        if action is None:
            return "copy"

        if action in _SKIP_ACTIONS:
            return "skip"

        if action == ActionType.COPY_FROM:
            return "copy_other"

        if action == ActionType.FIXED:
            return "fixed"

        if action == ActionType.OTHER:
            # Manual entries default to "manual" unless a fixed value exists
            return "fixed" if node.fixed_value else "manual"

        if action == ActionType.EXTENSION:
            # Treat extension like manual until more logic is defined
            return "manual"

        return "copy"

    def _collect_nodes(self, node: _FieldNode) -> None:
        for child in sorted(node.children.values(), key=lambda item: item.path):
            if child.intent == "skip":
                continue

            if child.intent in {"copy", "copy_other"}:
                if child.can_collapse and child.depth >= 2:
                    self._nodes_to_emit.append(child)
                else:
                    self._collect_nodes(child)
                continue

            if child.depth >= 2:
                self._nodes_to_emit.append(child)

    # ------------------------------------------------------------------
    # StructureMap sections
    # ------------------------------------------------------------------
    def _build_structure_section(self) -> list[dict]:
        structures: list[dict] = []
        for idx, profile in enumerate(self._mapping.sources or []):
            alias = self._source_aliases[idx]
            structures.append({"url": profile.url, "mode": "source", "alias": alias})

        target = self._mapping.target
        if target is not None:
            structures.append({"url": target.url, "mode": "target", "alias": self._target_alias})

        return structures

    def _build_inputs_section(self) -> list[dict]:
        inputs: list[dict] = []
        for alias in self._source_aliases:
            inputs.append({"name": alias, "type": alias, "mode": "source"})

        inputs.append({"name": self._target_alias, "type": self._target_alias, "mode": "target"})
        return inputs

    def _build_rule(self, node: _FieldNode) -> dict | None:
        relative_target = self._relative_path(node.path)
        if not relative_target:
            return None

        source_element = self._source_element(node)
        src_var = self._var_name("src", node.path)
        rule: dict = {
            "name": self._slug(node.path, suffix=self._stable_id(node.path)),
            "source": [
                {
                    "context": self._source_alias,
                    "element": source_element,
                    **({"variable": src_var} if node.intent in {"copy", "copy_other"} else {}),
                }
            ],
            "target": [],
        }

        documentation = self._build_documentation(node)
        if documentation:
            rule["documentation"] = documentation

        target_entry: dict
        if node.intent in {"copy", "copy_other"}:
            target_entry = {
                "context": self._target_alias,
                "contextType": "variable",
                "element": relative_target,
                "transform": "copy",
                "parameter": [{"valueId": src_var}],
            }
            rule["target"].append(target_entry)

        elif node.intent == "fixed":
            target_entry = {
                "context": self._target_alias,
                "contextType": "variable",
                "element": relative_target,
                "transform": "copy",
                "parameter": [{"valueString": node.fixed_value or ""}],
            }
            rule["target"].append(target_entry)

        else:  # manual fallback
            # Keep target empty – documentation points to manual work
            pass

        return rule

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _relative_path(self, path: str | None) -> str:
        if not path:
            return ""
        parts = path.split(".", 1)
        return parts[1] if len(parts) == 2 else ""

    def _source_element(self, node: _FieldNode) -> str:
        if node.intent == "copy_other" and node.other_path:
            other_rel = self._relative_path(node.other_path)
            if other_rel:
                return other_rel
        return self._relative_path(node.path)

    def _alias_from_name(self, name: str) -> str:
        return self._slug(name or "source", suffix="")

    def _compute_source_aliases(self) -> list[str]:
        aliases: list[str] = []
        sources = self._mapping.sources or []
        for idx, profile in enumerate(sources):
            if idx == 0:
                aliases.append(self._source_alias)
            else:
                aliases.append(self._alias_from_name(profile.name or f"source{idx}"))
        if not aliases:
            aliases.append(self._source_alias)
        return aliases

    def _slug(self, text: str, *, suffix: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "field"
        if suffix:
            return f"{cleaned}_{suffix}"
        return cleaned

    def _var_name(self, prefix: str, path: str) -> str:
        return f"{prefix}_{self._slug(path, suffix=self._stable_id(path))}"

    def _stable_id(self, text: str, length: int = 8) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]

    def _first_field_path(self) -> str | None:
        try:
            return next(iter(self._mapping.fields.keys()))
        except StopIteration:
            return None

    def _build_documentation(self, node: _FieldNode) -> str | None:
        details: list[str] = []
        intent_desc = {
            "copy": "Automatic copy",
            "copy_other": f"Copied from '{node.other_path}'" if node.other_path else "Automatic copy",
            "fixed": f"Fixed value '{node.fixed_value}'",
            "manual": "Manual action required",
        }.get(node.intent)
        if intent_desc:
            details.append(intent_desc)
        if node.remark:
            details.append(node.remark)
        return " | ".join(details) if details else None

