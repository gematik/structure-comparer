from .action import Action

REMARKS = {
    Action.USE: "Property and value(s) will be retained",
    Action.USE_RECURSIVE: "Property and all child elements will be retained",
    Action.NOT_USE: "Property and value(s) will NOT be retained",
    Action.EMPTY: "Will remain empty for now, as no source information is available",
    Action.MANUAL: "",
    Action.COPY_VALUE_FROM: "Value copied from '{}'",
    Action.COPY_VALUE_TO: "Value copied to '{}'",
    Action.FIXED: "Set to '{}' fixed value",
    Action.COPY_NODE_TO: "Node will be transferred to '{}'",
    Action.COPY_NODE_FROM: "Node will be received from '{}'",
}

DESCRIPTIONS = {
    Action.USE: "Property and value(s) will be RETAINED",
    Action.USE_RECURSIVE: "Property and ALL CHILD ELEMENTS will be RETAINED",
    Action.NOT_USE: "Property and value(s) will NOT be retained",
    Action.EMPTY: "Will remain EMPTY for now, as no source information is available",
    Action.MANUAL: "Make your own NOTE",
    Action.COPY_VALUE_FROM: "Value(s) will be COPIED FROM another field",
    Action.COPY_VALUE_TO: "Value(s) will be COPIED TO another field",
    Action.FIXED: "Value will be FIXED",
    Action.COPY_NODE_TO: "Node (extension) will be TRANSFERRED to target field",
    Action.COPY_NODE_FROM: "Node (extension) will be RECEIVED from source field",
}
