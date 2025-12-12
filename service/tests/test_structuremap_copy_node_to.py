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

    assert "Organization.telecom" in emitted_paths
    assert "Organization.telecom:eMail" not in emitted_paths
