from enum import StrEnum


class Action(StrEnum):
    USE = "use"
    USE_RECURSIVE = "use_recursive"
    NOT_USE = "not_use"
    EMPTY = "empty"
    MANUAL = "manual"
    COPY_VALUE_FROM = "copy_value_from"
    COPY_VALUE_TO = "copy_value_to"
    FIXED = "fixed"
    COPY_NODE_TO = "copy_node_to"
    COPY_NODE_FROM = "copy_node_from"
