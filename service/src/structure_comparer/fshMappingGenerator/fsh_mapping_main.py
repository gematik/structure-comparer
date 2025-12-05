"""StructureMap export helpers.

The service stores mapping instructions on a field-by-field basis.  This module
turns those instructions into ``StructureMap`` JSON representations that can be
served directly or converted to FSH later on.  Besides single-map exports the
module is now able to emit *packages* that contain a router StructureMap plus
per-source StructureMaps when a mapping references multiple source profiles.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Iterable, Literal, Sequence, Optional

from structure_comparer.model.mapping_action_models import ActionInfo

from .naming import normalize_ruleset_name, slug, stable_id, var_name
from .nodes import FieldNode
from .rule_builder import StructureMapRuleBuilder
from .tree_builder import FieldTreeBuilder
from ..utils.structuremap_helpers import alias_from_profile

if TYPE_CHECKING:  # pragma: no cover - only used for type checking
    from structure_comparer.data.mapping import Mapping
    from structure_comparer.data.profile import Profile
    from structure_comparer.data.transformation import Transformation, TransformationField
    from structure_comparer.data.project import Project


STRUCTUREMAP_PACKAGE_VERSION = 1
STRUCTUREMAP_URL_PREFIX = "https://gematik.de/fhir/structure-comparer/StructureMap/"


@dataclass(frozen=True)
class StructureMapArtifact:
    """Description of a generated StructureMap artifact."""

    name: str
    filename: str
    content: str
    kind: Literal["router", "mapping", "transformation"]
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


def _transformation_filename(transformation: "Transformation") -> str:
    label = transformation.name or transformation.id or "transformation"
    clean_label = slug(label, suffix="") or "Transformation"
    return f"StructureMap-transformation-{clean_label}.json"


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


def _structuremap_input_type(profile: "Profile" | None, *, alias: str | None = None) -> str:
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


def build_transformation_structuremap_artifact(
    *,
    transformation: "Transformation",
    project: "Project",
    ruleset_name: str | None = None,
) -> StructureMapArtifact:
    """Build a StructureMap artifact for a Transformation definition."""

    builder = _TransformationStructureMapBuilder(
        transformation=transformation,
        project=project,
        ruleset_name=ruleset_name,
    )
    structure_map = builder.build()
    filename = _transformation_filename(transformation)
    target_profile = getattr(transformation, "target", None)

    return StructureMapArtifact(
        name=structure_map["name"],
        filename=filename,
        content=json.dumps(structure_map, indent=2, ensure_ascii=False),
        kind="transformation",
        structure_map_url=structure_map.get("url"),
        mapping_id=transformation.id,
        mapping_name=getattr(transformation, "name", None),
        ruleset_name=structure_map["name"],
        target_profile_url=getattr(target_profile, "url", None),
        target_profile_name=getattr(target_profile, "name", None),
    )


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
        return _structuremap_input_type(profile, alias=alias)

    def _first_field_path(self) -> str | None:
        try:
            return next(iter(self._mapping.fields.keys()))
        except StopIteration:
            return None

    def _alias_from_name(self, name: str) -> str:
        return slug(name or "source", suffix="")


@dataclass(frozen=True)
class _TransformationPathSegment:
    name: str
    slice_name: str | None = None


@dataclass(frozen=True)
class _TransformationPath:
    raw: str
    root: str | None
    segments: list[_TransformationPathSegment]

    @classmethod
    def parse(cls, path: str | None) -> "_TransformationPath":
        if not path:
            return cls(raw="", root=None, segments=[])
        cleaned = path.strip()
        if not cleaned:
            return cls(raw="", root=None, segments=[])
        root = None
        remainder = cleaned
        if cleaned.startswith("."):
            remainder = cleaned[1:]
        elif "." in cleaned:
            root, remainder = cleaned.split(".", 1)
        else:
            root = cleaned
            remainder = ""

        segments: list[_TransformationPathSegment] = []
        if remainder:
            for part in remainder.split('.'):
                token = part.strip()
                if not token:
                    continue
                if ":" in token:
                    name, slice_name = token.split(":", 1)
                else:
                    name, slice_name = token, None
                segments.append(_TransformationPathSegment(name=name or "segment", slice_name=slice_name or None))

        return cls(raw=cleaned, root=root, segments=segments)

    def last_segment(self) -> _TransformationPathSegment | None:
        return self.segments[-1] if self.segments else None


@dataclass(frozen=True)
class _TransformationTargetPlan:
    container_entries: list[dict]
    name_rules: list[dict]
    resource_parent: str
    resource_variable: str
    resource_parameters: list[dict]


class _TransformationTargetBuilder:
    def __init__(
        self,
        *,
        target_alias: str,
        target_path: _TransformationPath,
        mapping: "Mapping",
        default_source_context: str,
    ) -> None:
        self._target_alias = target_alias or "target"
        self._target_path = target_path
        self._mapping = mapping
        self._default_source_context = default_source_context or self._target_alias

    def build(self) -> _TransformationTargetPlan | None:
        if not self._target_path.segments:
            return None
        if self._target_path.last_segment() is None:
            return None

        *container_segments, resource_segment = self._target_path.segments
        if resource_segment.name != "resource":
            return None

        container_entries: list[dict] = []
        name_rules: list[dict] = []
        context = self._target_alias
        for idx, segment in enumerate(container_segments):
            element = segment.name or "element"
            variable = var_name("target", f"{self._target_path.raw}_{idx}_{element}")
            entry = {
                "context": context,
                "contextType": "variable",
                "element": element,
                "variable": variable,
            }
            container_entries.append(entry)
            if segment.slice_name:
                rule_name = normalize_ruleset_name(f"set_{element}_{segment.slice_name}_name")
                name_rules.append(
                    {
                        "name": rule_name,
                        "source": [{"context": self._default_source_context}],
                        "target": [
                            {
                                "context": variable,
                                "contextType": "variable",
                                "element": "name",
                                "transform": "copy",
                                "parameter": [{"valueString": segment.slice_name}],
                            }
                        ],
                    }
                )
            context = variable

        resource_parent = context
        resource_variable = var_name("target", f"{self._target_path.raw}_resource")
        target_profile = getattr(self._mapping.target, "url", None) or getattr(self._mapping.target, "resource_type", None) or "Resource"
        resource_parameters = [{"valueString": target_profile}]

        return _TransformationTargetPlan(
            container_entries=container_entries,
            name_rules=name_rules,
            resource_parent=resource_parent,
            resource_variable=resource_variable,
            resource_parameters=resource_parameters,
        )


class _TransformationFieldRuleBuilder:
    def __init__(
        self,
        *,
        field: "TransformationField",
        mapping: "Mapping",
        source_alias: str,
        target_alias: str,
    ) -> None:
        self._field = field
        self._mapping = mapping
        self._source_alias = source_alias or "source"
        self._target_alias = target_alias or "target"
        ruleset = f"{mapping.id.replace('-', '_')}_structuremap"
        self._child_ruleset_name = _ensure_valid_structuremap_name(ruleset)
        self.structure_map_url = f"{STRUCTUREMAP_URL_PREFIX}{self._child_ruleset_name}"

    def build(self) -> dict | None:
        if not self._field.other:
            return None
        source_path = _TransformationPath.parse(self._field.name)
        target_path = _TransformationPath.parse(self._field.other)

        source_clauses, source_var, first_source_var = self._build_source_clauses(source_path)
        if source_var is None:
            return None

        target_builder = _TransformationTargetBuilder(
            target_alias=self._target_alias,
            target_path=target_path,
            mapping=self._mapping,
            default_source_context=first_source_var or source_var,
        )
        target_plan = target_builder.build()
        if target_plan is None:
            return None

        resource_entry = {
            "context": target_plan.resource_parent,
            "contextType": "variable",
            "element": "resource",
            "variable": target_plan.resource_variable,
            "transform": "create",
            "parameter": target_plan.resource_parameters,
        }

        call_rule = {
            "name": normalize_ruleset_name(f"call_{self._child_ruleset_name}"),
            "source": [{"context": source_var}],
            "target": [resource_entry],
            "dependent": [
                {
                    "name": self._child_ruleset_name,
                    "variable": [source_var, target_plan.resource_variable],
                }
            ],
        }

        rule_children = [*target_plan.name_rules, call_rule]
        documentation = f"{self._field.name} -> {self._field.other} using {getattr(self._mapping, 'name', self._mapping.id)}"

        return {
            "name": normalize_ruleset_name(f"{self._field.name or 'field'}_{stable_id(self._field.other or 'target')}")[:64],
            "documentation": documentation,
            "source": source_clauses,
            "target": target_plan.container_entries,
            "rule": rule_children,
        }

    def _build_source_clauses(
        self,
        path: _TransformationPath,
    ) -> tuple[list[dict], str | None, str | None]:
        clauses: list[dict] = []
        context = self._source_alias
        final_var: str | None = None
        first_var: str | None = None

        if not path.segments:
            variable = var_name("source", self._field.name or self._mapping.id)
            clauses.append({"context": context, "variable": variable})
            return clauses, variable, variable

        segments = path.segments
        for idx, segment in enumerate(segments):
            element = segment.name.split(":", 1)[0] if segment.name else "element"
            variable = var_name("source", f"{self._field.name}_{idx}_{element}")
            clause: dict[str, str] = {"context": context, "variable": variable}
            if element:
                clause["element"] = element
            if segment.slice_name and element == "entry" and idx + 1 < len(segments) and segments[idx + 1].name == "resource":
                source_type = self._mapping.sources[0].resource_type if self._mapping.sources else None
                if source_type:
                    clause["condition"] = f"resource is {source_type}"
            clauses.append(clause)
            context = variable
            final_var = variable
            if first_var is None:
                first_var = variable

        return clauses, final_var, first_var or final_var


class _TransformationStructureMapBuilder:
    def __init__(
        self,
        *,
        transformation: "Transformation",
        project: "Project",
        ruleset_name: str | None,
    ) -> None:
        self._transformation = transformation
        self._project = project
        requested = ruleset_name or transformation.name or transformation.id or "TransformationMap"
        self._ruleset_name = _ensure_valid_structuremap_name(requested)
        self._target_profile = getattr(transformation, "target", None)
        self._target_alias = alias_from_profile(self._target_profile, "target")
        self._source_profiles = list(getattr(transformation, "sources", []) or [])
        self._source_aliases = self._build_source_aliases()
        self._default_source_alias = next(iter(self._source_aliases.values()), "source")
        self._imports: set[str] = set()

    def build(self) -> dict:
        structure_entries = self._build_structure_section()
        inputs = self._build_inputs_section()
        rules = self._build_rules()

        result: dict = {
            "resourceType": "StructureMap",
            "id": self._ruleset_name,
            "url": f"{STRUCTUREMAP_URL_PREFIX}{self._ruleset_name}",
            "name": self._ruleset_name,
            "status": getattr(self._transformation, "status", None) or "draft",
            "version": getattr(self._transformation, "version", None),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "description": f"Auto-generated StructureMap for transformation {getattr(self._transformation, 'name', self._transformation.id)}",
            "structure": structure_entries,
            "group": [
                {
                    "name": self._ruleset_name,
                    "typeMode": "types" if all(item.get("type") for item in inputs) else "none",
                    "documentation": f"Transformation generated for {getattr(self._transformation, 'name', self._transformation.id)}",
                    "input": inputs,
                    "rule": rules,
                }
            ],
        }
        if self._imports:
            result["import"] = sorted(self._imports)
        return result

    def _build_source_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for idx, profile in enumerate(self._source_profiles):
            if profile and getattr(profile, "key", None):
                aliases[profile.key] = alias_from_profile(profile, f"source{idx + 1}")
        if not aliases:
            aliases["__default__"] = "source"
        return aliases

    def _build_structure_section(self) -> list[dict]:
        entries: list[dict] = []
        for profile in self._source_profiles:
            if getattr(profile, "url", None):
                alias = self._source_aliases.get(profile.key, self._default_source_alias)
                entries.append({"url": profile.url, "mode": "source", "alias": alias})
        if getattr(self._target_profile, "url", None):
            entries.append({"url": self._target_profile.url, "mode": "target", "alias": self._target_alias})
        return entries

    def _build_inputs_section(self) -> list[dict]:
        inputs: list[dict] = []
        if self._source_profiles:
            for profile in self._source_profiles:
                alias = self._source_aliases.get(profile.key, self._default_source_alias)
                inputs.append({"name": alias, "type": _structuremap_input_type(profile), "mode": "source"})
        else:
            inputs.append({"name": self._default_source_alias, "type": "Resource", "mode": "source"})
        inputs.append({"name": self._target_alias, "type": _structuremap_input_type(self._target_profile), "mode": "target"})
        return inputs

    def _build_rules(self) -> list[dict]:
        rules: list[dict] = []
        for field in getattr(self._transformation, "fields", {}).values():
            if not getattr(field, "map", None):
                continue
            mapping = getattr(self._project, "mappings", {}).get(field.map)
            if mapping is None:
                continue
            source_alias = self._resolve_source_alias(field)
            builder = _TransformationFieldRuleBuilder(
                field=field,
                mapping=mapping,
                source_alias=source_alias,
                target_alias=self._target_alias,
            )
            rule = builder.build()
            if rule:
                rules.append(rule)
                if builder.structure_map_url:
                    self._imports.add(builder.structure_map_url)
        return rules

    def _resolve_source_alias(self, field: "TransformationField") -> str:
        for profile in self._source_profiles:
            if field.profiles.get(profile.key):
                return self._source_aliases.get(profile.key, self._default_source_alias)
        return self._default_source_alias

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

