from __future__ import annotations

from dataclasses import dataclass, field

from structure_comparer.model.mapping_action_models import ActionType


@dataclass(slots=True)
class FieldNode:
    """Tree node describing a mapping field."""

    segment: str
    path: str
    parent: FieldNode | None = None
    action: ActionType | None = None
    other_path: str | None = None
    fixed_value: str | None = None
    remark: str | None = None
    intent: str = "copy"  # copy | copy_other | fixed | manual | skip
    collapse_kind: tuple[str, str | None] | None = None
    can_collapse: bool = False
    force_container: bool = False
    children: dict[str, "FieldNode"] = field(default_factory=dict)

    @property
    def depth(self) -> int:
        return 0 if not self.path else len(self.path.split("."))
