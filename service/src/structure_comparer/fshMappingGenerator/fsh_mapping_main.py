"""StructureMap export helpers.

The service stores mapping instructions on a field-by-field basis.  This module
turns those instructions into a ``StructureMap`` JSON representation that can be
served directly or converted to FSH later on.  The JSON format is easier to
validate and aligns with the FastAPI download endpoint that expects textual
content.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING

from structure_comparer.model.mapping_action_models import ActionInfo

from .naming import normalize_ruleset_name, slug, stable_id
from .nodes import FieldNode
from .rule_builder import StructureMapRuleBuilder
from .tree_builder import FieldTreeBuilder

if TYPE_CHECKING:  # pragma: no cover - only used for type checking
    from structure_comparer.data.mapping import Mapping



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
        self._ruleset_name = normalize_ruleset_name(ruleset_name or "structuremap")
        self._target_profile_key = mapping.target.key if mapping.target else None
        self._source_profile_keys = [p.key for p in mapping.sources or []]

        self._source_inputs = self._compute_source_inputs()
        self._target_input = self._compute_target_input()
        self._field_source_support: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self) -> dict:
        tree_builder = FieldTreeBuilder(
            mapping=self._mapping,
            actions=self._actions,
            target_profile_key=self._target_profile_key,
            source_profile_keys=self._source_profile_keys,
        )
        tree_result = tree_builder.build()
        nodes_to_emit = list(tree_result.nodes_to_emit)
        self._field_source_support = tree_result.field_source_support

        if not nodes_to_emit:
            first_path = self._first_field_path()
            if first_path:
                fallback_node = FieldNode(segment=first_path.split(".")[-1], path=first_path)
                fallback_node.intent = "copy"
                fallback_node.can_collapse = True
                fallback_node.collapse_kind = ("copy", None)
                nodes_to_emit.append(fallback_node)

        rule_builder = StructureMapRuleBuilder(
            mapping=self._mapping,
            actions=self._actions,
            source_alias=self._source_alias,
            target_alias=self._target_alias,
            target_profile_key=self._target_profile_key,
            source_profile_keys=self._source_profile_keys,
            field_source_support=self._field_source_support,
        )
        rules = [rule_builder.build_rule(node) for node in nodes_to_emit]
        rules = [rule for rule in rules if rule is not None]

        return {
            "resourceType": "StructureMap",
            "id": slug(self._ruleset_name, suffix=stable_id(self._ruleset_name)),
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

    def _first_field_path(self) -> str | None:
        try:
            return next(iter(self._mapping.fields.keys()))
        except StopIteration:
            return None

    def _alias_from_name(self, name: str) -> str:
        return slug(name or "source", suffix="")

