from pydantic import BaseModel

from ..action import Action as ActionEnum
from ..consts import DESCRIPTIONS, REMARKS


class Action(BaseModel):
    value: ActionEnum
    remark: str
    description: str

    @staticmethod
    def from_enum(value: ActionEnum) -> "Action":
        return Action(
            value=value.value, remark=REMARKS[value], description=DESCRIPTIONS[value]
        )


class ActionOutput(BaseModel):
    actions: list[Action]

    @staticmethod
    def from_enum():
        actions = [Action.from_enum(a) for a in ActionEnum]
        return ActionOutput(actions=actions)
