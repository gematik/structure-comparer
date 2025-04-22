from .action import Action

REMARKS = {
    Action.USE: "Property and value(s) will be retained",
    Action.NOT_USE: "Property and value(s) will NOT be retained",
    Action.EMPTY: "Will remain empty for now, as no source information is available",
    Action.EXTENSION: "Extension and value(s) will be retained",
    Action.MANUAL: "",
    Action.COPY_FROM: "Mapped from '{}'",
    Action.COPY_TO: "Mapped to '{}'",
    Action.FIXED: "Set to '{}' fixed value",
    Action.MEDICATION_SERVICE: "Set by the Medication Service",
}

INSTRUCTIONS = {
    Action.USE: "Property and value(s) will be RETAINED",
    Action.NOT_USE: "Property and value(s) will NOT be retained",
    Action.EMPTY: "Will remain EMPTY for now, as no source information is available",
    Action.EXTENSION: "Extension and value(s) will be RETAINED",
    Action.MANUAL: "Make your own NOTE",
    Action.COPY_FROM: "Value(s) will be MAPPED FROM another field",
    Action.COPY_TO: "Value(s) will be MAPPED TO another field",
    Action.FIXED: "Value will be FIXED",
    Action.MEDICATION_SERVICE: "Value set by the MEDICATION SERVICE",
}
