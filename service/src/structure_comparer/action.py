from enum import StrEnum


class Action(StrEnum):
    USE = "use"
    NOT_USE = "not_use"
    EMPTY = "empty"
    MANUAL = "manual"
    COPY_FROM = "copy_from"
    COPY_TO = "copy_to"
    FIXED = "fixed"
