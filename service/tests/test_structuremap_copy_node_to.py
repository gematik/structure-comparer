from structure_comparer.fshMappingGenerator.tree_builder import FieldTreeBuilder
from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource, ActionType


class _DummyProfileField:
    def __init__(self, *, max_num: int | str = 1) -> None:
        self.max_num = max_num


class _DummyField:
    def __init__(self) -> None:
        self.profiles: dict[str, _DummyProfileField] = {}


class _DummyMapping:
    def __init__(self, fields: dict[str, _DummyField]) -> None:
        self.fields = fields


def _field_with_profiles(keys: list[str]) -> _DummyField:
    field = _DummyField()
    for key in keys:
        field.profiles[key] = _DummyProfileField()
    return field


def test_copy_node_slice_redirect_to_parent_is_skipped() -> None:
    target_key = "target"
    source_key = "source"
    fields = {
        "Organization.telecom": _field_with_profiles([target_key, source_key]),
        "Organization.telecom:eMail": _field_with_profiles([target_key, source_key]),
    }
    mapping = _DummyMapping(fields)
    actions = {
        "Organization.telecom": ActionInfo(action=ActionType.USE, source=ActionSource.MANUAL),
        "Organization.telecom:eMail": ActionInfo(
            action=ActionType.COPY_NODE_TO,
            source=ActionSource.MANUAL,
            other_value="Organization.telecom",
        ),
    }

    builder = FieldTreeBuilder(
        mapping=mapping,
        actions=actions,
        target_profile_key=target_key,
        source_profile_keys=[source_key],
    )

    result = builder.build()
    emitted_paths = [node.path for node in result.nodes_to_emit]
    assert emitted_paths == []


def test_manual_action_is_not_emitted_as_rule() -> None:
    target_key = "target"
    source_key = "source"
    fields = {
        "Organization.name": _field_with_profiles([target_key, source_key]),
    }
    mapping = _DummyMapping(fields)
    actions = {
        "Organization.name": ActionInfo(action=ActionType.MANUAL, source=ActionSource.MANUAL),
    }

    builder = FieldTreeBuilder(
        mapping=mapping,
        actions=actions,
        target_profile_key=target_key,
        source_profile_keys=[source_key],
    )

    result = builder.build()

    assert result.nodes_to_emit == []


def test_copy_node_from_is_non_emitting_and_relies_on_source_counterpart() -> None:
    target_key = "target"
    source_key = "source"
    source_path = "Organization.identifier:Telematik-ID"
    target_path = "Organization.identifier:TelematikID"
    fields = {
        source_path: _field_with_profiles([target_key, source_key]),
        target_path: _field_with_profiles([target_key, source_key]),
    }
    mapping = _DummyMapping(fields)
    actions = {
        source_path: ActionInfo(
            action=ActionType.COPY_NODE_TO,
            source=ActionSource.MANUAL,
            other_value=target_path,
        ),
        target_path: ActionInfo(
            action=ActionType.COPY_NODE_FROM,
            source=ActionSource.MANUAL,
            other_value=source_path,
        ),
    }

    builder = FieldTreeBuilder(
        mapping=mapping,
        actions=actions,
        target_profile_key=target_key,
        source_profile_keys=[source_key],
    )

    result = builder.build()
    emitted_paths = [node.path for node in result.nodes_to_emit]

    assert source_path in emitted_paths
    assert target_path not in emitted_paths
