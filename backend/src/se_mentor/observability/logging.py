from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from se_mentor.security.redaction import redact_text


class LogCategory(StrEnum):
    API = "API"
    AGENT = "AGENT"
    LLM = "LLM"
    GOVERNANCE = "GOVERNANCE"
    TOOL = "TOOL"
    VALIDATION = "VALIDATION"


@dataclass(frozen=True)
class StructuredLogEvent:
    task_id: str
    correlation_id: str
    category: LogCategory
    level: str
    message: str
    payload: dict[str, Any]


class StructuredLogger:
    def __init__(self) -> None:
        self.events: list[StructuredLogEvent] = []

    def emit(self, event: StructuredLogEvent) -> StructuredLogEvent:
        sanitized = StructuredLogEvent(
            task_id=event.task_id,
            correlation_id=event.correlation_id,
            category=event.category,
            level=event.level.upper(),
            message=redact_text(event.message),
            payload={key: _sanitize_value(value) for key, value in event.payload.items()},
        )
        self.events.append(sanitized)
        return sanitized


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = redact_text(value)
        return redacted if len(redacted) <= 600 else redacted[:587].rstrip() + "\n[truncated]"
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
