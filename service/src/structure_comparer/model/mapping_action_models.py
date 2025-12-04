"""Domain models for mapping actions and evaluation (Step 3).

These models are introduced as part of the mapping-action rewrite initiative.
They are currently used by the experimental mapping action / evaluation engines
and corresponding unit tests. Existing production endpoints remain unchanged.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class ActionType(str, Enum):
    """Semantic action types supported by the new mapping action engine."""

    USE = "use"
    USE_RECURSIVE = "use_recursive"
    NOT_USE = "not_use"
    EMPTY = "empty"
    COPY_FROM = "copy_from"
    COPY_TO = "copy_to"
    FIXED = "fixed"
    MANUAL = "manual"  # User provides free-text implementation instructions in remark field
    EXTENSION = "extension"  # For source extensions to be copied to any target field


class ActionSource(str, Enum):
    """Origin of a mapping action applied to a field."""

    MANUAL = "manual"
    INHERITED = "inherited"
    SYSTEM_DEFAULT = "system_default"


class EvaluationSeverity(str, Enum):
    """Severity level for individual evaluation reasons."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EvaluationStatus(str, Enum):
    """Overall evaluation outcome for a field."""

    OK = "ok"
    ACTION_REQUIRED = "action_required"
    RESOLVED = "resolved"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
    EVALUATION_FAILED = "evaluation_failed"


class MappingStatus(str, Enum):
    """Unified mapping status surfaced to clients."""

    INCOMPATIBLE = "incompatible"
    WARNING = "warning"
    SOLVED = "solved"
    COMPATIBLE = "compatible"


class ActionInfo(BaseModel):
    """Effective mapping action for a single field.

    Convention:
    - action = None: No action has been selected yet. User must make a decision.
                     This is typically the case for fields with 'warning' or 'incompatible'
                     classification where no default action can be automatically determined.
    - action = ActionType value: An action has been determined (either manually set,
                                  inherited from parent, or auto-determined as system default).
    - action = 'manual' (in legacy system): User has set a manual action with a remark field
                                             containing implementation instructions.
    """

    action: ActionType | None
    source: ActionSource

    inherited_from: Optional[str] = None
    auto_generated: bool = False

    user_remark: Optional[str] = None
    system_remark: Optional[str] = None  # Deprecated: Use system_remarks instead
    system_remarks: Optional[list[str]] = None  # Multiple system remarks for detailed information

    fixed_value: Optional[Any] = None
    other_value: Optional[Any] = None

    raw_manual_entry: Optional[Dict[str, Any]] = None


class EvaluationReason(BaseModel):
    """Structured reason emitted by the evaluation engine."""

    code: str
    severity: EvaluationSeverity
    message_key: str
    details: Dict[str, Any] = {}
    related_action: Optional[ActionType] = None


class EvaluationResult(BaseModel):
    """Aggregated evaluation state for a field."""

    status: EvaluationStatus
    reasons: list[EvaluationReason] = []

    has_warnings: bool = False
    has_errors: bool = False

    summary_key: Optional[str] = None
    mapping_status: MappingStatus
