from __future__ import annotations

from typing import Any

from structure_comparer.model.mapping_action_models import ActionInfo

from .extension_utils import find_skipped_slices, get_extension_url, is_extension_path
from .naming import slug, stable_id, var_name
from .nodes import FieldNode
from .tree_builder import SKIP_ACTIONS


class StructureMapRuleBuilder:
    """Builds StructureMap rule dictionaries from prepared nodes."""

    def __init__(
        self,
        *,
        mapping,
        actions: dict[str, ActionInfo],
        source_alias: str,
        target_alias: str,
        target_profile_key: str | None,
        source_profile_keys: list[str],
        field_source_support: dict[str, bool],
    ) -> None:
        self._mapping = mapping
        self._actions = actions
        self._source_alias = source_alias
        self._target_alias = target_alias
        self._target_profile_key = target_profile_key
        self._source_profile_keys = source_profile_keys
        self._field_source_support = field_source_support

    def build_rule(self, node: FieldNode, parent_src: dict | None = None, parent_tgt: dict | None = None) -> dict | None:
        if parent_src and parent_tgt:
            return self._build_relative_rule(node, parent_src, parent_tgt)
        return self._build_root_rule(node)

    # ------------------------------------------------------------------
    # Relative rule building (child recursion)
    # ------------------------------------------------------------------
    def _build_relative_rule(self, node: FieldNode, parent_src: dict, parent_tgt: dict) -> dict | None:
        rule_name = slug(node.path, suffix=stable_id(node.path))

        src_element = node.segment.split(":")[0]
        if src_element.endswith("[x]"):
            src_element = src_element[:-3]

        tgt_element = node.segment
        parts = tgt_element.split(":")
        if parts[0].endswith("[x]"):
            parts[0] = parts[0][:-3]
        tgt_element = ":".join(parts)

        if node.intent == "copy_to" and node.other_path:
            tgt_element = node.other_path.split(".")[-1]
            parts = tgt_element.split(":")
            if parts[0].endswith("[x]"):
                parts[0] = parts[0][:-3]
            tgt_element = ":".join(parts)

        src_var = var_name("src", node.path)
        tgt_var = var_name("tgt", node.path)

        source_entry: dict[str, Any] = {
            "context": parent_src["variable"],
            "element": src_element,
            "variable": src_var,
        }

        skipped_urls = find_skipped_slices(
            node,
            self._actions,
            self._mapping,
            self._target_profile_key,
            SKIP_ACTIONS,
        )
        if skipped_urls:
            conditions = [f"url != '{url}'" for url in skipped_urls]
            source_entry["condition"] = " and ".join(conditions)

        target_entry: dict[str, Any] = {
            "context": parent_tgt["variable"],
            "contextType": "variable",
            "element": tgt_element,
            "variable": tgt_var,
            "transform": "copy",
            "parameter": [{"valueId": src_var}],
        }

        if node.intent == "fixed":
            target_entry["transform"] = "copy"
            target_entry["parameter"] = [{"valueString": node.fixed_value or ""}]

        rule = {
            "name": rule_name,
            "source": [source_entry],
            "target": [target_entry],
        }

        if is_extension_path(node.path) and node.intent in {"copy", "copy_other", "copy_to"}:
            src_path = node.path
            tgt_path = node.other_path if node.intent == "copy_to" else node.path
            target_url = get_extension_url(self._mapping, tgt_path, self._target_profile_key)
            source_url = get_extension_url(self._mapping, src_path, self._source_profile_keys)

            if target_url and source_url and target_url != source_url:
                rule["target"].append(
                    {
                        "context": tgt_var,
                        "contextType": "variable",
                        "element": "url",
                        "transform": "copy",
                        "parameter": [{"valueString": target_url}],
                    }
                )

        if node.children:
            sub_rules = []
            for child in sorted(node.children.values(), key=lambda item: item.path):
                if child.intent == "skip":
                    continue
                sub_rule = self.build_rule(child, source_entry, target_entry)
                if sub_rule:
                    sub_rules.append(sub_rule)
            if sub_rules:
                rule["rule"] = sub_rules

        return rule

    # ------------------------------------------------------------------
    # Top-level rule building
    # ------------------------------------------------------------------
    def _build_root_rule(self, node: FieldNode) -> dict | None:
        relative_target = self._relative_path(node.path)
        if not relative_target:
            return None

        rule_name = slug(node.path, suffix=stable_id(node.path))
        documentation = self._build_documentation(node)

        source_chain: list[dict] = []
        target_chain: list[dict] = []

        if node.intent in {"copy", "copy_other", "copy_to"}:
            source_path = self._source_path_for_node(node)
            target_path = node.path

            if node.intent == "copy_to":
                source_path = node.path
                target_path = node.other_path or node.path

            source_chain = self._build_path_chain(source_path, alias=self._source_alias, prefix="src")
            if not source_chain:
                return None

            skipped_urls = find_skipped_slices(
                node,
                self._actions,
                self._mapping,
                self._target_profile_key,
                SKIP_ACTIONS,
            )
            conditions = [f"url != '{url}'" for url in skipped_urls]

            if is_extension_path(source_path):
                source_url = get_extension_url(self._mapping, source_path, self._source_profile_keys)
                if source_url:
                    conditions.append(f"url = '{source_url}'")

            if conditions:
                condition_str = " and ".join(conditions)
                if "condition" in source_chain[-1]:
                    source_chain[-1]["condition"] += f" and {condition_str}"
                else:
                    source_chain[-1]["condition"] = condition_str

            target_chain = self._build_path_chain(target_path, alias=self._target_alias, prefix="tgt")
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
            source_entry = {
                "context": leaf_source["context"],
                "element": leaf_source["element"],
                "variable": leaf_source["variable"],
            }
            if "condition" in leaf_source:
                source_entry["condition"] = leaf_source["condition"]
            rule["source"] = [source_entry]
        else:
            rule["source"] = [{"context": self._source_alias}]

        if node.intent in {"copy", "copy_other", "copy_to"}:
            leaf_source = source_chain[-1]
            leaf_target = target_chain[-1]

            is_extension = is_extension_path(node.path)
            use_create = is_extension and bool(node.children)

            target_url = None
            source_url = None
            if is_extension:
                src_p = source_path
                tgt_p = target_path
                target_url = get_extension_url(self._mapping, tgt_p, self._target_profile_key)
                source_url = get_extension_url(self._mapping, src_p, self._source_profile_keys)

            if use_create:
                create_type = "Extension"
                rule["target"] = [
                    {
                        "context": leaf_target["context"],
                        "contextType": "variable",
                        "element": leaf_target["element"],
                        "variable": leaf_target["variable"],
                        "transform": "create",
                        "parameter": [{"valueString": create_type}],
                    }
                ]
            else:
                rule["target"] = [
                    {
                        "context": leaf_target["context"],
                        "contextType": "variable",
                        "element": leaf_target["element"],
                        "variable": leaf_target["variable"],
                        "transform": "copy",
                        "parameter": [{"valueId": leaf_source["variable"]}],
                    }
                ]

            if is_extension:
                if target_url and (use_create or (source_url and target_url != source_url)):
                    rule["target"].append(
                        {
                            "context": leaf_target["variable"],
                            "contextType": "variable",
                            "element": "url",
                            "transform": "copy",
                            "parameter": [{"valueString": target_url}],
                        }
                    )

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

        if node.children:
            leaf_src_var = source_chain[-1]["variable"] if source_chain else None
            leaf_tgt_var = target_chain[-1]["variable"] if target_chain else None

            if leaf_src_var and leaf_tgt_var:
                sub_rules = []
                for child in sorted(node.children.values(), key=lambda item: item.path):
                    if child.intent == "skip":
                        continue
                    sub_rule = self.build_rule(child, {"variable": leaf_src_var}, {"variable": leaf_tgt_var})
                    if sub_rule:
                        sub_rules.append(sub_rule)
                if sub_rules:
                    rule["rule"] = sub_rules

        if source_chain:
            rule = self._wrap_with_chain(rule, source_chain[:-1], direction="source")
        if target_chain:
            rule = self._wrap_with_chain(rule, target_chain[:-1], direction="target")

        return rule

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _source_path_for_node(self, node: FieldNode) -> str | None:
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
            variable = var_name(prefix, f"{alias}.{partial}")

            element_name = segment.split(":")[0]
            resolved_type = None
            current_full_path = f"{root}.{partial}"

            field = self._mapping.fields.get(current_full_path)
            if field and self._target_profile_key:
                target_field = field.profiles.get(self._target_profile_key)
                if target_field:
                    data = getattr(target_field, "_ProfileField__data", None)
                    if data and data.type:
                        for entry in data.type:
                            if entry.code == "Extension" and entry.profile:
                                resolved_type = entry.profile[0]
                                break
                        if (
                            not resolved_type
                            and segment.split(":")[0].endswith("[x]")
                            and len(data.type) == 1
                        ):
                            resolved_type = data.type[0].code

            base_name = element_name.split(":")[0]

            if base_name.endswith("[x]"):
                current_field = self._mapping.fields.get(current_full_path)
                if current_field and self._target_profile_key:
                    target_field = current_field.profiles.get(self._target_profile_key)
                    if target_field:
                        data = getattr(target_field, "_ProfileField__data", None)
                        if data and data.type and len(data.type) == 1:
                            resolved_type = data.type[0].code

                base_name = base_name[:-3]

                if ":" in element_name:
                    parts = element_name.split(":")
                    parts[0] = base_name
                    element_name = ":".join(parts)
                else:
                    element_name = base_name

            chain.append({
                "context": context,
                "element": element_name,
                "variable": variable,
                "type": resolved_type,
            })
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

    def _relative_path(self, path: str | None) -> str:
        if not path:
            return ""
        parts = path.split(".", 1)
        return parts[1] if len(parts) == 2 else ""

    def _build_documentation(self, node: FieldNode) -> str | None:
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
