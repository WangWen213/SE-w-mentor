from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from se_mentor.contracts.actions import (
    AgentAction,
    AgentActionAdapter,
    DeleteFileAction,
    ReadFileAction,
)
from se_mentor.contracts.enums import FeedbackKind, FeedbackSeverity
from se_mentor.contracts.feedback import FeedbackSignal

_SHELL_PROGRAMS = {"bash", "sh", "cmd", "powershell", "pwsh"}


class ParseOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ActionParseResult:
    outcome: ParseOutcome
    action: AgentAction | None
    feedback: FeedbackSignal | None
    error_detail: str | None = None


class AgentActionParser:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)

    def parse(self, payload: dict[str, Any]) -> ActionParseResult:
        try:
            action = AgentActionAdapter.validate_python(payload)
        except ValidationError as exc:
            first_error = exc.errors()[0]
            location = ".".join(str(part) for part in first_error.get("loc", ())) or "<root>"
            return _rejected(
                f"invalid agent action: {first_error['type']} at {location}",
                error_detail=str(first_error)[:512],
            )
        if _has_invalid_path(action):
            return _rejected("invalid path")
        if getattr(action, "action_type", None) and action.__class__.__name__ == "RunCommandAction":
            parameters = getattr(action, "parameters", None)
            program = str(getattr(parameters, "program", "")).lower()
            args = [str(arg).lower() for arg in getattr(parameters, "args", [])]
            if program in _SHELL_PROGRAMS or any(arg in {"-lc", "/c"} for arg in args):
                return _rejected("free-text shell is not accepted")
        return ActionParseResult(ParseOutcome.ACCEPTED, action, None)


def _has_invalid_path(action: AgentAction) -> bool:
    parameters = getattr(action, "parameters", None)
    if isinstance(action, ReadFileAction | DeleteFileAction) or hasattr(parameters, "path"):
        path = Path(str(parameters.path))
        return path.is_absolute() or ".." in path.parts
    return False


def _rejected(message: str, *, error_detail: str | None = None) -> ActionParseResult:
    return ActionParseResult(
        ParseOutcome.REJECTED,
        None,
        FeedbackSignal(
            kind=FeedbackKind.TOOL,
            severity=FeedbackSeverity.ERROR,
            message=message,
        ),
        error_detail,
    )
