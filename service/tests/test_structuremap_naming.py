"""Tests for StructureMap naming and canonical URL generation."""

from __future__ import annotations

import json
from collections import OrderedDict

import pytest  # type: ignore[import-not-found]

from structure_comparer.fshMappingGenerator import fsh_mapping_main as generator


class _DummyFieldTreeResult:
    root = None
    nodes_to_emit = ["dummy"]
    field_source_support: dict[str, bool] = {}


class _DummyFieldTreeBuilder:
    def __init__(self, **_: object) -> None:  # pragma: no cover - trivial stub
        pass

    def build(self) -> _DummyFieldTreeResult:  # pragma: no cover - trivial stub
        return _DummyFieldTreeResult()


class _DummyRuleBuilder:
    def __init__(self, **_: object) -> None:  # pragma: no cover - trivial stub
        pass

    def build_rule(self, node: object) -> dict:
        return {"name": f"rule_for_{node}"}


class DummyProfile:
    def __init__(self, name: str, key: str, resource_type: str = "Patient") -> None:
        self.name = name
        self.key = key
        self.url = f"https://example.org/StructureDefinition/{name}"
        self.version = "1.0"
        self.resource_type = resource_type


class DummyMapping:
    def __init__(self, *, sources: list[DummyProfile], target: DummyProfile) -> None:
        self.sources = sources
        self.target = target
        self.name = "Demo Mapping"
        self.status = "draft"
        self.version = "1.0"
        self.id = "mapping-123"
        self.fields = OrderedDict({"root.field": object()})


@pytest.fixture(autouse=True)
def stub_structuremap_builders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use dummy builders so we can focus on naming logic."""

    monkeypatch.setattr(generator, "FieldTreeBuilder", _DummyFieldTreeBuilder)
    monkeypatch.setattr(generator, "StructureMapRuleBuilder", _DummyRuleBuilder)


def _build_package(sources: list[str]) -> generator.StructureMapPackage:
    source_profiles = [DummyProfile(name, f"source-{idx}") for idx, name in enumerate(sources, start=1)]
    target_profile = DummyProfile("TargetProfile", "target")
    mapping = DummyMapping(sources=source_profiles, target=target_profile)
    return generator.build_structuremap_package(
        mapping=mapping,
        actions={},
        source_alias="source",
        target_alias="target",
        ruleset_name="customRuleset",
    )


def test_single_source_structuremap_uses_profile_name_and_canonical_url() -> None:
    package = _build_package(["SourceAlpha"])
    assert len(package.artifacts) == 1

    structure_map = json.loads(package.artifacts[0].content)
    assert structure_map["id"] == "SourceAlphaMap"
    assert structure_map["name"] == "SourceAlphaMap"
    assert (
        structure_map["url"]
        == "https://gematik.de/fhir/structure-comparer/StructureMap/SourceAlphaMap"
    )


def test_router_structuremap_uses_target_name_and_children_inherit_source_names() -> None:
    package = _build_package(["Alpha", "Beta"])
    assert len(package.artifacts) == 3  # router + two child maps

    router_map = json.loads(package.artifacts[0].content)
    assert router_map["id"] == "TargetProfileMap"
    assert (
        router_map["url"]
        == "https://gematik.de/fhir/structure-comparer/StructureMap/TargetProfileMap"
    )

    child_ids = {json.loads(artifact.content)["id"] for artifact in package.artifacts[1:]}
    assert child_ids == {"AlphaMap", "BetaMap"}

    route_rules = router_map["group"][0]["rule"]
    conditions = [rule["source"][0]["condition"] for rule in route_rules]
    assert conditions == [
        "meta.profile.where($this.contains('Alpha')).exists()",
        "meta.profile.where($this.contains('Beta')).exists()",
    ]
