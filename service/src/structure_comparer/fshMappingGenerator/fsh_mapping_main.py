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
STRUCTUREMAP_URL_PREFIX = "https://gematik.de/fhir/structure-comparer/StructureMap/"


@dataclass(frozen=True)
class StructureMapArtifact:
    """Description of a generated StructureMap artifact."""

    name: str
    filename: str
    content: str
    kind: Literal["router", "mapping"]
    structure_map_url: str | None
    mapping_id: str
    mapping_name: str | None
    ruleset_name: str
    source_profile_url: str | None = None
    source_profile_name: str | None = None
    target_profile_url: str | None = None
    target_profile_name: str | None = None

    def manifest_entry(self, *, filename: str | None = None) -> dict:
        return {
            "name": self.name,
            "filename": filename or self.filename,
            "kind": self.kind,
            "structureMapUrl": self.structure_map_url,
            "mappingId": self.mapping_id,
            "mappingName": self.mapping_name,
            "rulesetName": self.ruleset_name,
            "sourceProfileUrl": self.source_profile_url,
            "sourceProfileName": self.source_profile_name,
            "targetProfileUrl": self.target_profile_url,
            "targetProfileName": self.target_profile_name,
        }


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
        package_root: str | None = None,
    ) -> dict:
        generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "packageVersion": STRUCTUREMAP_PACKAGE_VERSION,
            "generatedAt": generated_at,
            "mappingId": mapping_id,
            "projectKey": project_key,
            "rulesetName": ruleset_name,
            "packageRoot": package_root or ".",
            "artifacts": [artifact.manifest_entry() for artifact in self.artifacts],
        }


def _profile_label(profile: "Profile" | None, fallback: str) -> str:
    if profile is None:
        return fallback
    for attr in ("name", "key", "id", "url"):
        value = getattr(profile, attr, None)
        if value:
            return value
    return fallback


def _profile_slug(profile: "Profile" | None, fallback: str) -> str:
    label = _profile_label(profile, fallback)
    return slug(label, suffix="") or fallback


def _base_filename(
    *,
    source_profile: "Profile" | None,
    target_profile: "Profile" | None,
    kind: Literal["router", "mapping"],
) -> str:
    target_slug = _profile_slug(target_profile, "Target")
    if kind == "router":
        return f"StructureMap-router-to-{target_slug}"

    source_slug = _profile_slug(source_profile, "Source")
    return f"StructureMap-{source_slug}-to-{target_slug}"


def _unique_filename(base: str, registry: dict[str, int]) -> str:
    counter = registry.get(base, 0)
    registry[base] = counter + 1
    suffix = "" if counter == 0 else f"-{counter + 1}"
    return f"{base}{suffix}.json"


def _unique_structuremap_name(base_name: str, registry: dict[str, int]) -> str:
    base = base_name or "StructureMapMap"
    counter = registry.get(base, 0)
    registry[base] = counter + 1
    if counter == 0:
        candidate = base[:64]
    else:
        suffix = f"{counter + 1}"
        max_base_len = max(1, 64 - len(suffix))
        candidate = f"{base[:max_base_len]}{suffix}"

    if candidate and candidate[0].isdigit():
        candidate = f"F{candidate[:-1]}" if len(candidate) == 64 else f"F{candidate}"

    return candidate[:64] or "StructureMap"


def _structuremap_name_from_profile(
    profile: "Profile" | None,
    *,
    fallback: str,
    registry: dict[str, int],
) -> str:
    base_label = _profile_slug(profile, fallback)
    max_base_len = max(1, 64 - len("Map"))
    base_name = f"{base_label[:max_base_len]}Map"
    return _unique_structuremap_name(base_name, registry)


def _structuremap_name_for_router(
    mapping: "Mapping",
    *,
    registry: dict[str, int],
    fallback: str | None = None,
) -> str:
    target_label = _profile_slug(getattr(mapping, "target", None), fallback or getattr(mapping, "name", "Router"))
    max_base_len = max(1, 64 - len("Map"))
    base = f"{target_label[:max_base_len]}Map"
    return _unique_structuremap_name(base, registry)


def _ensure_valid_structuremap_name(name: str) -> str:
    sanitized = slug(name or "StructureMap", suffix="")
    if not sanitized:
        sanitized = "StructureMap"
    return sanitized[:64]



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
    use_alias_for_input_type: bool = True,
) -> dict:
    builder = _StructureMapBuilder(
        mapping=mapping,
        actions=actions,
        source_alias=source_alias,
        target_alias=target_alias,
        ruleset_name=ruleset_name,
        source_profiles=source_profiles,
        use_alias_for_input_type=use_alias_for_input_type,
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

    sources = list(mapping.sources or [])
    target_profile = mapping.target
    target_profile_url = getattr(target_profile, "url", None)
    target_profile_name = getattr(target_profile, "name", None)

    artifacts: list[StructureMapArtifact] = []
    filename_registry: dict[str, int] = {}
    ruleset_registry: dict[str, int] = {}
    requested_ruleset = ruleset_name or mapping.name or mapping.id

    if len(sources) <= 1:
        primary_profile = sources[0] if sources else target_profile
        structuremap_name = _structuremap_name_from_profile(
            primary_profile,
            fallback=requested_ruleset,
            registry=ruleset_registry,
        )
        structure_map = build_structuremap_dict(
            mapping=mapping,
            actions=actions,
            source_alias=source_alias,
            target_alias=target_alias,
            ruleset_name=structuremap_name,
            source_profiles=sources or None,
        )
        source_profile = sources[0] if sources else None
        filename = _unique_filename(
            _base_filename(
                source_profile=source_profile,
                target_profile=target_profile,
                kind="mapping",
            ),
            filename_registry,
        )
        artifacts.append(
            StructureMapArtifact(
                name=structure_map["name"],
                filename=filename,
                content=json.dumps(structure_map, indent=2, ensure_ascii=False),
                kind="mapping",
                structure_map_url=structure_map.get("url"),
                mapping_id=mapping.id,
                mapping_name=getattr(mapping, "name", None),
                ruleset_name=structure_map["name"],
                source_profile_url=getattr(source_profile, "url", None),
                source_profile_name=getattr(source_profile, "name", None),
                target_profile_url=target_profile_url,
                target_profile_name=target_profile_name,
            )
        )
        return StructureMapPackage(artifacts=artifacts)

    child_refs: list[dict] = []
    for index, profile in enumerate(sources):
        child_ruleset = _structuremap_name_from_profile(
            profile,
            fallback=f"{requested_ruleset}_{index + 1}" if requested_ruleset else f"source_{index + 1}",
            registry=ruleset_registry,
        )
        structure_map = build_structuremap_dict(
            mapping=mapping,
            actions=actions,
            source_alias=source_alias,
            target_alias=target_alias,
            ruleset_name=child_ruleset,
            source_profiles=[profile],
            use_alias_for_input_type=False,
        )
        filename = _unique_filename(
            _base_filename(
                source_profile=profile,
                target_profile=target_profile,
                kind="mapping",
            ),
            filename_registry,
        )
        artifacts.append(
            StructureMapArtifact(
                name=structure_map["name"],
                filename=filename,
                content=json.dumps(structure_map, indent=2, ensure_ascii=False),
                kind="mapping",
                structure_map_url=structure_map.get("url"),
                mapping_id=mapping.id,
                mapping_name=getattr(mapping, "name", None),
                ruleset_name=structure_map["name"],
                source_profile_url=profile.url,
                source_profile_name=getattr(profile, "name", None),
                target_profile_url=target_profile_url,
                target_profile_name=target_profile_name,
            )
        )
        child_refs.append(
            {
                "profile": profile,
                "ruleset_name": structure_map["name"],
                "structure_map_url": structure_map.get("url"),
                "source_input_type": structure_map["group"][0]["input"][0].get("type"),
            }
        )

    router_map = _build_router_structuremap(
        mapping=mapping,
        ruleset_name=_structuremap_name_for_router(mapping, registry=ruleset_registry, fallback=requested_ruleset),
        source_alias=source_alias,
        target_alias=target_alias,
        child_refs=child_refs,
    )
    router_filename = _unique_filename(
        _base_filename(source_profile=None, target_profile=target_profile, kind="router"),
        filename_registry,
    )
    artifacts.insert(
        0,
        StructureMapArtifact(
            name=router_map["name"],
            filename=router_filename,
            content=json.dumps(router_map, indent=2, ensure_ascii=False),
            kind="router",
            structure_map_url=router_map.get("url"),
            mapping_id=mapping.id,
            mapping_name=getattr(mapping, "name", None),
            ruleset_name=router_map["name"],
            target_profile_url=target_profile_url,
            target_profile_name=target_profile_name,
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
        use_alias_for_input_type: bool = True,
    ) -> None:
        self._mapping = mapping
        self._actions = actions
        self._source_alias = source_alias or "source"
        self._target_alias = target_alias or "target"
        self._ruleset_name = _ensure_valid_structuremap_name(ruleset_name or "StructureMap")
        self._target_profile_key = mapping.target.key if mapping.target else None
        self._source_profiles = list(source_profiles) if source_profiles is not None else list(mapping.sources or [])
        self._source_profile_keys = [p.key for p in self._source_profiles]
        self._use_alias_for_input_type = use_alias_for_input_type

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
            "id": self._ruleset_name,
            "url": f"{STRUCTUREMAP_URL_PREFIX}{self._ruleset_name}",
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
                    "type": self._input_type_for_profile(
                        profile,
                        alias=alias if self._use_alias_for_input_type else None,
                    ),
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
            "type": self._input_type_for_profile(
                profile,
                alias=self._target_alias if self._use_alias_for_input_type else None,
            ),
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
    router_id = _ensure_valid_structuremap_name(ruleset_name)
    imports = [ref["structure_map_url"] for ref in child_refs if ref.get("structure_map_url")]

    shared_resource_type = _shared_resource_type(mapping.sources or [])
    source_structure_url = _canonical_url_for_resource_type(shared_resource_type)
    target_structure_url = target_url or _canonical_url_for_resource_type(getattr(target, "resource_type", None))

    structure_entries: list[dict] = []
    if source_structure_url:
        structure_entries.append({"url": source_structure_url, "mode": "source", "alias": source_alias})
    if target_structure_url:
        structure_entries.append({"url": target_structure_url, "mode": "target", "alias": target_alias})

    source_input_type = source_alias or shared_resource_type or "Resource"
    target_input_type = target_alias or getattr(target, "resource_type", None) or "Resource"

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
                source_input_type=ref.get("source_input_type"),
            )
            for ref in child_refs
        ],
    }

    router_map = {
        "resourceType": "StructureMap",
        "id": router_id,
        "url": f"{STRUCTUREMAP_URL_PREFIX}{router_id}",
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


def _build_router_rule(
    *,
    profile: "Profile",
    source_alias: str,
    target_alias: str,
    child_ruleset_name: str,
    source_input_type: str | None = None,
) -> dict:
    profile_name = getattr(profile, "name", None) or profile.url
    condition = _router_condition_for_profile(profile)
    route_rule_name = normalize_ruleset_name(f"route_{profile_name}")
    invoke_rule_name = normalize_ruleset_name(f"call_{child_ruleset_name}")
    typed_variable = slug(f"{source_alias}_{profile_name or 'source'}", suffix="Routed")
    source_clause: dict[str, str] = {
        "context": source_alias,
        "condition": condition,
    }
    dependent_source_context = source_alias
    if source_input_type:
        source_clause["type"] = source_input_type
        source_clause["variable"] = typed_variable
        dependent_source_context = typed_variable
    return {
        "name": route_rule_name,
        "documentation": f"Routes resources constrained by {profile_name}",
        "source": [source_clause],
        "rule": [
            {
                "name": invoke_rule_name,
                "source": [{"context": dependent_source_context}],
                "dependent": [
                    {
                        "name": child_ruleset_name,
                        "variable": [dependent_source_context, target_alias],
                    }
                ],
            }
        ],
    }


def _router_condition_for_profile(profile: "Profile") -> str:
    match_value = _profile_match_fragment(profile)
    escaped_value = _escape_fhirpath_string(match_value)
    return f"meta.profile.where($this.contains('{escaped_value}')).exists()"


def _profile_match_fragment(profile: "Profile") -> str:
    url = getattr(profile, "url", "") or ""
    fragment = url
    if url:
        fragment = url.split("|", 1)[0]
        if "/" in fragment:
            fragment = fragment.rsplit("/", 1)[-1] or fragment

    if not fragment:
        fragment = getattr(profile, "name", None) or getattr(profile, "key", None) or url

    return fragment or "profile"


def _escape_fhirpath_string(value: str) -> str:
    if not value:
        return value
    return value.replace("\\", "\\\\").replace("'", "\\'")


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

