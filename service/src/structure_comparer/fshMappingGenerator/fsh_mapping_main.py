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
        self._ruleset_name = self._normalize_name(ruleset_name or "structuremap")
        self._target_profile_key = mapping.target.key if mapping.target else None
        self._source_profile_keys = [p.key for p in mapping.sources or []]

        self._root = _FieldNode(segment="", path="")
        self._nodes_to_emit: list[_FieldNode] = []
        self._source_inputs = self._compute_source_inputs()
        self._target_input = self._compute_target_input()
        self._blocked_prefixes: set[str] = set()
        self._field_source_support: dict[str, bool] = {}

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
                    "typeMode": self._group_type_mode(),
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
            return True
        if "[x]" in relative and ":" not in relative:
            return True
        return False

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
        if info.action in _SKIP_ACTIONS:
            return False
        if info.action in {ActionType.FIXED, ActionType.EXTENSION}:
            return False
        if info.action == ActionType.MANUAL and info.fixed_value:
            return False
        if info.action == ActionType.COPY_FROM:
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

        # Special handling for extension mapping when source/target canonical URLs differ
        if (
            current.action == ActionType.COPY_FROM
            and self._is_extension_path(path)
            and not path.endswith(".url")
        ):
            self._ensure_extension_url_fix(current)

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
        if action is None and self._is_extension_path(node.path):
            return "skip"

        if action is None:
            return "copy"

        if action in _SKIP_ACTIONS:
            return "skip"

        if action == ActionType.COPY_FROM:
            return "copy_other"

        if action == ActionType.FIXED:
            return "fixed"

        if action == ActionType.MANUAL:
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
        for item in self._source_inputs:
            profile = item["profile"]
            if profile is None:
                continue
            structures.append({"url": profile.url, "mode": "source", "alias": item["alias"]})

        target_profile = self._target_input["profile"]
        if target_profile is not None:
            structures.append({"url": target_profile.url, "mode": "target", "alias": self._target_input["alias"]})

        return structures

    def _build_inputs_section(self) -> list[dict]:
        inputs: list[dict] = []
        for item in self._source_inputs:
            inputs.append({"name": item["alias"], "type": item["type"], "mode": "source"})

        inputs.append({"name": self._target_input["alias"], "type": self._target_input["type"], "mode": "target"})
        return inputs

    def _group_type_mode(self) -> str:
        inputs = [*self._source_inputs, self._target_input]
        if all(input_info.get("type") for input_info in inputs):
            return "types"
        return "none"

    def _build_rule(self, node: _FieldNode) -> dict | None:
        relative_target = self._relative_path(node.path)
        if not relative_target:
            return None

        rule_name = self._slug(node.path, suffix=self._stable_id(node.path))
        documentation = self._build_documentation(node)

        source_chain: list[dict] = []
        target_chain: list[dict] = []

        if node.intent in {"copy", "copy_other"}:
            source_chain = self._build_path_chain(self._source_path_for_node(node), alias=self._source_alias, prefix="src")
            if not source_chain:
                return None
            target_chain = self._build_path_chain(node.path, alias=self._target_alias, prefix="tgt")
            if not target_chain:
                return None
        elif node.intent == "fixed":
            target_chain = self._build_path_chain(node.path, alias=self._target_alias, prefix="tgt")
            if not target_chain:
                return None
            if self._field_source_support.get(node.path, True):
                source_chain = self._build_path_chain(node.path, alias=self._source_alias, prefix="src")

        rule: dict = {"name": rule_name}
        if documentation:
            rule["documentation"] = documentation

        if source_chain:
            leaf_source = source_chain[-1]
            rule["source"] = [
                {
                    "context": leaf_source["context"],
                    "element": leaf_source["element"],
                    "variable": leaf_source["variable"],
                }
            ]
        else:
            rule["source"] = [{"context": self._source_alias}]

        if node.intent in {"copy", "copy_other"}:
            leaf_source = source_chain[-1]
            leaf_target = target_chain[-1]
            rule["target"] = [
                {
                    "context": leaf_target["context"],
                    "contextType": "variable",
                    "element": leaf_target["element"],
                    "transform": "copy",
                    "parameter": [{"valueId": leaf_source["variable"]}],
                }
            ]
        elif node.intent == "fixed":
            leaf_target = target_chain[-1]
            rule["target"] = [
                {
                    "context": leaf_target["context"],
                    "contextType": "variable",
                    "element": leaf_target["element"],
                    "transform": "copy",
                    "parameter": [{"valueString": node.fixed_value or ""}],
                }
            ]

        rule = self._wrap_with_chain(rule, source_chain[:-1], direction="source") if source_chain else rule
        rule = self._wrap_with_chain(rule, target_chain[:-1], direction="target") if target_chain else rule

        return rule

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _relative_path(self, path: str | None) -> str:
        if not path:
            return ""
        parts = path.split(".", 1)
        return parts[1] if len(parts) == 2 else ""

    def _source_path_for_node(self, node: _FieldNode) -> str | None:
        if node.intent == "copy_other" and node.other_path:
            return node.other_path
        return node.path

    def _build_path_chain(self, path: str | None, *, alias: str, prefix: str) -> list[dict]:
        relative = self._relative_path(path)
        if not relative:
            return []

        segments = [segment for segment in relative.split(".") if segment]
        chain: list[dict] = []
        context = alias
        
        root = path.split(".")[0] if path else ""

        for idx, segment in enumerate(segments):
            partial = ".".join(segments[: idx + 1])
            variable = self._var_name(prefix, f"{alias}.{partial}")
            
            # Strip slice name from element name for FHIR compliance
            element_name = segment.split(":")[0]
            
            # Handle [x] suffix
            resolved_type = None
            if element_name.endswith("[x]"):
                # Try to resolve type from target profile
                current_full_path = f"{root}.{partial}"
                
                field = self._mapping.fields.get(current_full_path)
                if field and self._target_profile_key:
                    target_field = field.profiles.get(self._target_profile_key)
                    if target_field:
                        # Access underlying ElementDefinition
                        ed = getattr(target_field, "_ProfileField__data", None)
                        if ed and ed.type and len(ed.type) == 1:
                            type_code = ed.type[0].code
                            resolved_type = type_code
                
                # Always strip [x]
                element_name = element_name[:-3]
            
            chain.append({"context": context, "element": element_name, "variable": variable, "type": resolved_type})
            context = variable
        return chain

    def _wrap_with_chain(self, rule: dict, chain: list[dict], *, direction: str) -> dict:
        if not chain:
            return rule

        wrapped_rule = rule
        for entry in reversed(chain):
            wrapper_entry = {
                "context": entry["context"],
                "element": entry["element"],
                "variable": entry["variable"],
            }
            if direction == "target":
                wrapper_entry["contextType"] = "variable"
                if entry.get("type"):
                    wrapper_entry["transform"] = "create"
                    wrapper_entry["parameter"] = [{"valueString": entry["type"]}]

            documentation = wrapped_rule.pop("documentation", None)
            wrapped_rule = {
                "name": wrapped_rule.get("name"),
                direction: [wrapper_entry],
                "rule": [wrapped_rule],
            }
            if direction == "target":
                wrapped_rule["source"] = [{"context": self._source_alias}]

            if documentation:
                wrapped_rule["documentation"] = documentation

        return wrapped_rule
        if not chain:
            return rule

        wrapped_rule = rule
        for entry in reversed(chain):
            wrapper_entry = {
                "context": entry["context"],
                "element": entry["element"],
                "variable": entry["variable"],
            }
            if direction == "target":
                wrapper_entry["contextType"] = "variable"

            documentation = wrapped_rule.pop("documentation", None)
            wrapped_rule = {
                "name": wrapped_rule.get("name"),
                direction: [wrapper_entry],
                "rule": [wrapped_rule],
            }
            if direction == "target":
                wrapped_rule["source"] = [{"context": self._source_alias}]

            if documentation:
                wrapped_rule["documentation"] = documentation

        return wrapped_rule

    def _alias_from_name(self, name: str) -> str:
        return self._slug(name or "source", suffix="")

    def _compute_source_inputs(self) -> list[dict]:
        inputs: list[dict] = []
        sources = self._mapping.sources or []
        for idx, profile in enumerate(sources):
            alias = self._source_alias if idx == 0 else self._alias_from_name(profile.name or f"source{idx}")
            inputs.append(
                {
                    "alias": alias,
                    "profile": profile,
                    "type": self._input_type_for_profile(profile, alias=alias),
                }
            )
        if not inputs:
            inputs.append({"alias": self._source_alias, "profile": None, "type": "Resource"})
        return inputs

    def _compute_target_input(self) -> dict:
        profile = self._mapping.target
        return {
            "alias": self._target_alias,
            "profile": profile,
            "type": self._input_type_for_profile(profile, alias=self._target_alias),
        }

    def _input_type_for_profile(self, profile, *, alias: str | None = None) -> str:
        if alias:
            return alias
        if profile is None:
            return "Resource"
        resource_type = getattr(profile, "resource_type", None)
        if resource_type:
            return resource_type
        canonical = getattr(profile, "url", None)
        version = getattr(profile, "version", None)
        if canonical:
            return f"{canonical}|{version}" if version else canonical
        if getattr(profile, "name", None):
            return profile.name
        return "Resource"

    def _slug(self, text: str, *, suffix: str) -> str:
        base = self._camelize(text)
        if suffix:
            max_base_len = max(1, 64 - len(suffix))
            base = base[:max_base_len]
            candidate = f"{base}{suffix}"
        else:
            candidate = base[:64]

        if candidate[0].isdigit():
            candidate = f"F{candidate[:-1]}" if len(candidate) == 64 else f"F{candidate}"
        return candidate

    def _var_name(self, prefix: str, path: str) -> str:
        slug = self._slug(path, suffix=self._stable_id(path))
        candidate = f"{prefix}{slug[0].upper()}{slug[1:]}" if slug else prefix
        return candidate[:64]

    def _camelize(self, text: str) -> str:
        parts = re.split(r"[^A-Za-z0-9]+", text)
        parts = [part for part in parts if part]
        if not parts:
            return "Field"

        first = parts[0]
        camel = first[0].upper() + first[1:]
        for part in parts[1:]:
            camel += part.capitalize()
        if not camel:
            camel = "Field"
        return camel

    def _stable_id(self, text: str, length: int = 8) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]

    def _normalize_name(self, text: str) -> str:
        slug = self._slug(text, suffix="")
        return slug or "StructureMap"

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

    def _is_extension_path(self, path: str | None) -> bool:
        if not path:
            return False
        return ".extension" in path

    def _ensure_extension_url_fix(self, node: _FieldNode) -> None:
        target_url = self._get_extension_url(node.path, self._target_profile_key)
        source_url = self._get_extension_url(node.other_path, self._source_profile_keys)
        if not target_url or not source_url or target_url == source_url:
            return

        url_node = self._ensure_node(f"{node.path}.url")
        url_node.action = ActionType.FIXED
        url_node.fixed_value = target_url
        if not url_node.remark:
            url_node.remark = "Set canonical URL for extension"

    def _get_extension_url(self, path: str | None, profile_keys) -> str | None:
        if not path:
            return None

        field = self._mapping.fields.get(path)
        if field is None:
            return None

        keys = profile_keys
        if isinstance(profile_keys, str) or profile_keys is None:
            keys = [profile_keys]

        for key in keys or []:
            if not key:
                continue
            profile_field = field.profiles.get(key)
            if profile_field is None:
                continue
            data = getattr(profile_field, "_ProfileField__data", None)
            if data is None:
                continue
            type_list = getattr(data, "type", None) or []
            for item in type_list:
                profiles = getattr(item, "profile", None) or []
                if profiles:
                    return profiles[0]
        return None

