from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from se_mentor.security.redaction import redact_text

PERF_LOG_FILENAME = "perf-runtime.log"
PERF_LOG_HANDLER_NAME = "se_mentor.perf_runtime_file"


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


class PerfLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "[perf]" in record.getMessage()


def configure_runtime_logging(runtime_dir: str | Path | None = None) -> Path:
    target_dir = Path(runtime_dir) if runtime_dir is not None else _default_runtime_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = (target_dir / PERF_LOG_FILENAME).resolve()
    logger = logging.getLogger("se_mentor")
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    logger.propagate = True

    existing = _perf_file_handler(logger, log_path)
    if existing is None:
        existing = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        existing.set_name(PERF_LOG_HANDLER_NAME)
        logger.addHandler(existing)
    existing.setLevel(logging.INFO)
    existing.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    if not any(isinstance(item, PerfLogFilter) for item in existing.filters):
        existing.addFilter(PerfLogFilter())
    return log_path


def _default_runtime_dir() -> Path:
    return Path(__file__).resolve().parents[3] / ".sementor"


def _perf_file_handler(logger: logging.Logger, log_path: Path) -> logging.FileHandler | None:
    for handler in logger.handlers:
        if not isinstance(handler, logging.FileHandler):
            continue
        base_filename = getattr(handler, "baseFilename", None)
        if base_filename is not None and Path(base_filename).resolve() == log_path:
            return handler
    return None


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = redact_text(value)
        return redacted if len(redacted) <= 600 else redacted[:587].rstrip() + "\n[truncated]"
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
