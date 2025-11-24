"""StructureMap export helpers.

The service stores mapping instructions on a field-by-field basis.  This module
turns those instructions into ``StructureMap`` JSON representations that can be
served directly or converted to FSH later on.  Besides single-map exports the
module is now able to emit *packages* that contain a router StructureMap plus
per-source StructureMaps when a mapping references multiple source profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Iterable, Literal, Sequence

from structure_comparer.model.mapping_action_models import ActionInfo

from .naming import normalize_ruleset_name, slug, stable_id, var_name
from .nodes import FieldNode
from .rule_builder import StructureMapRuleBuilder
from .tree_builder import FieldTreeBuilder

if TYPE_CHECKING:  # pragma: no cover - only used for type checking
    from structure_comparer.data.mapping import Mapping
    from structure_comparer.data.profile import Profile


STRUCTUREMAP_PACKAGE_VERSION = 1
STRUCTUREMAP_PACKAGE_ROOT_PREFIX = "structuremaps"


@dataclass(frozen=True)
class StructureMapArtifact:
    """Description of a generated StructureMap artifact."""

    name: str
    filename: str
    content: str
    kind: Literal["router", "mapping"]
    structure_map_url: str | None
    source_profile_url: str | None = None
    source_profile_name: str | None = None


@dataclass(frozen=True)
class StructureMapPackage:
    """Wrapper that groups multiple StructureMap artifacts for download."""

    artifacts: list[StructureMapArtifact]

    def manifest(
        self,
        *,
        mapping_id: str,
        project_key: str | None,
        ruleset_name: str,
        package_root: str,
    ) -> dict:
        generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "packageVersion": STRUCTUREMAP_PACKAGE_VERSION,
            "generatedAt": generated_at,
            "mappingId": mapping_id,
            "projectKey": project_key,
            "rulesetName": ruleset_name,
            "packageRoot": package_root,
            "artifacts": [
                {
                    "name": artifact.name,
                    "filename": artifact.filename,
                    "kind": artifact.kind,
                    "structureMapUrl": artifact.structure_map_url,
                    "sourceProfileUrl": artifact.source_profile_url,
                    "sourceProfileName": artifact.source_profile_name,
                }
                for artifact in self.artifacts
            ],
        }


def default_package_root(mapping_id: str) -> str:
    """Return the default folder name used inside ZIP downloads."""

    safe_mapping_id = slug(mapping_id or STRUCTUREMAP_PACKAGE_ROOT_PREFIX, suffix="")
    return f"{STRUCTUREMAP_PACKAGE_ROOT_PREFIX}-{safe_mapping_id}"



def build_structuremap_fsh(
    mapping: "Mapping",
    actions: dict[str, ActionInfo],
    *,
    source_alias: str,
    target_alias: str,
    ruleset_name: str,
    source_profile: "Profile" | None = None,
) -> str:
    """Build a StructureMap JSON string based on mapping actions."""

    structure_map = build_structuremap_dict(
        mapping=mapping,
        actions=actions,
        source_alias=source_alias,
        target_alias=target_alias,
        ruleset_name=ruleset_name,
        source_profiles=[source_profile] if source_profile else None,
    )
    return json.dumps(structure_map, indent=2, ensure_ascii=False)


def build_structuremap_dict(
    *,
    mapping: "Mapping",
    actions: dict[str, ActionInfo],
    source_alias: str,
    target_alias: str,
    ruleset_name: str,
    source_profiles: Sequence["Profile"] | None = None,
) -> dict:
    builder = _StructureMapBuilder(
        mapping=mapping,
        actions=actions,
        source_alias=source_alias,
        target_alias=target_alias,
        ruleset_name=ruleset_name,
        source_profiles=source_profiles,
    )
    return builder.build()


def build_structuremap_package(
    mapping: "Mapping",
    actions: dict[str, ActionInfo],
    *,
    source_alias: str,
    target_alias: str,
    ruleset_name: str,
) -> StructureMapPackage:
    """Build a StructureMap package.

    Returns a package that either contains a single StructureMap (one source
    profile) or a router StructureMap plus dedicated child StructureMaps per
    source profile.
    """

    normalized_ruleset = normalize_ruleset_name(ruleset_name or "structuremap")
    sources = list(mapping.sources or [])
    artifacts: list[StructureMapArtifact] = []

    if len(sources) <= 1:
        structure_map = build_structuremap_dict(
            mapping=mapping,
            actions=actions,
            source_alias=source_alias,
            target_alias=target_alias,
            ruleset_name=normalized_ruleset,
            source_profiles=sources or None,
        )
        artifacts.append(
            StructureMapArtifact(
                name=structure_map["name"],
                filename=f"{structure_map['name']}.json",
                content=json.dumps(structure_map, indent=2, ensure_ascii=False),
                kind="mapping",
                structure_map_url=structure_map.get("url"),
                source_profile_url=sources[0].url if sources else None,
                source_profile_name=getattr(sources[0], "name", None) if sources else None,
            )
        )
        return StructureMapPackage(artifacts=artifacts)

    child_refs: list[dict] = []
    for index, profile in enumerate(sources):
        suffix = _profile_suffix(profile, index)
        child_ruleset = normalize_ruleset_name(f"{normalized_ruleset}_{suffix}")
        structure_map = build_structuremap_dict(
            mapping=mapping,
            actions=actions,
            source_alias=source_alias,
            target_alias=target_alias,
            ruleset_name=child_ruleset,
            source_profiles=[profile],
        )
        artifacts.append(
            StructureMapArtifact(
                name=structure_map["name"],
                filename=f"{structure_map['name']}.json",
                content=json.dumps(structure_map, indent=2, ensure_ascii=False),
                kind="mapping",
                structure_map_url=structure_map.get("url"),
                source_profile_url=profile.url,
                source_profile_name=getattr(profile, "name", None),
            )
        )
        child_refs.append(
            {
                "profile": profile,
                "ruleset_name": structure_map["name"],
                "structure_map_url": structure_map.get("url"),
            }
        )

    router_map = _build_router_structuremap(
        mapping=mapping,
        ruleset_name=normalized_ruleset,
        source_alias=source_alias,
        target_alias=target_alias,
        child_refs=child_refs,
    )
    artifacts.insert(
        0,
        StructureMapArtifact(
            name=router_map["name"],
            filename=f"{router_map['name']}.json",
            content=json.dumps(router_map, indent=2, ensure_ascii=False),
            kind="router",
            structure_map_url=router_map.get("url"),
        ),
    )
    return StructureMapPackage(artifacts=artifacts)


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
        source_profiles: Sequence["Profile"] | None = None,
    ) -> None:
        self._mapping = mapping
        self._actions = actions
        self._source_alias = source_alias or "source"
        self._target_alias = target_alias or "target"
        self._ruleset_name = normalize_ruleset_name(ruleset_name or "structuremap")
        self._target_profile_key = mapping.target.key if mapping.target else None
        self._source_profiles = list(source_profiles) if source_profiles is not None else list(mapping.sources or [])
        self._source_profile_keys = [p.key for p in self._source_profiles]

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

    def _compute_source_inputs(self) -> list[dict]:
        inputs: list[dict] = []
        sources = self._source_profiles or []
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


def _build_router_structuremap(
    *,
    mapping: "Mapping",
    ruleset_name: str,
    source_alias: str,
    target_alias: str,
    child_refs: Sequence[dict],
) -> dict:
    target = mapping.target
    target_url = getattr(target, "url", None)
    router_id = slug(ruleset_name, suffix=stable_id(ruleset_name))
    imports = [ref["structure_map_url"] for ref in child_refs if ref.get("structure_map_url")]

    shared_resource_type = _shared_resource_type(mapping.sources or [])
    source_structure_url = _canonical_url_for_resource_type(shared_resource_type)
    target_structure_url = target_url or _canonical_url_for_resource_type(getattr(target, "resource_type", None))

    structure_entries: list[dict] = []
    if source_structure_url:
        structure_entries.append({"url": source_structure_url, "mode": "source", "alias": source_alias})
    if target_structure_url:
        structure_entries.append({"url": target_structure_url, "mode": "target", "alias": target_alias})

    source_input_type = shared_resource_type or "Resource"
    target_input_type = getattr(target, "resource_type", None) or target_alias

    group_rule = {
        "name": ruleset_name,
        "typeMode": "none",
        "documentation": f"Router StructureMap for {mapping.name}",
        "input": [
            {"name": source_alias, "type": source_input_type, "mode": "source"},
            {"name": target_alias, "type": target_input_type, "mode": "target"},
        ],
        "rule": [
            _build_router_rule(
                profile=ref["profile"],
                source_alias=source_alias,
                target_alias=target_alias,
                child_ruleset_name=ref["ruleset_name"],
            )
            for ref in child_refs
        ],
    }

    router_map = {
        "resourceType": "StructureMap",
        "id": router_id,
        "url": f"{target_url}/StructureMap/{ruleset_name}" if target_url else f"StructureMap/{ruleset_name}",
        "name": ruleset_name,
        "status": mapping.status or "draft",
        "version": mapping.version,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "description": f"Router StructureMap for {mapping.name}",
        "structure": structure_entries,
        "group": [group_rule],
    }
    if imports:
        router_map["import"] = imports
    return router_map


def _build_router_rule(*, profile: "Profile", source_alias: str, target_alias: str, child_ruleset_name: str) -> dict:
    profile_name = getattr(profile, "name", None) or profile.url
    condition = f"meta.profile.exists(p | p = '{profile.url}')"
    route_rule_name = normalize_ruleset_name(f"route_{profile_name}")
    invoke_rule_name = normalize_ruleset_name(f"call_{child_ruleset_name}")
    return {
        "name": route_rule_name,
        "documentation": f"Routes resources constrained by {profile_name}",
        "source": [
            {
                "context": source_alias,
                "condition": condition,
            }
        ],
        "rule": [
            {
                "name": invoke_rule_name,
                "source": [{"context": source_alias}],
                "dependent": [
                    {
                        "name": child_ruleset_name,
                        "variable": [source_alias, target_alias],
                    }
                ],
            }
        ],
    }


def _shared_resource_type(profiles: Iterable["Profile"] | None) -> str | None:
    if not profiles:
        return None
    resource_types = {getattr(profile, "resource_type", None) for profile in profiles if getattr(profile, "resource_type", None)}
    if len(resource_types) == 1:
        return resource_types.pop()
    return None


def _canonical_url_for_resource_type(resource_type: str | None) -> str | None:
    if not resource_type:
        return None
    return f"http://hl7.org/fhir/StructureDefinition/{resource_type}"


def _profile_suffix(profile: "Profile", index: int) -> str:
    if getattr(profile, "name", None):
        return profile.name
    url = getattr(profile, "url", None)
    if url:
        return url.rstrip("/").split("/")[-1]
    return f"source{index}"

