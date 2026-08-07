from __future__ import annotations

import re
from collections.abc import Iterable
from re import Pattern


class RedactionError(RuntimeError):
    pass


DEFAULT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"LTAI[A-Za-z0-9]{8,}"),
    re.compile(r"(?:ghp_|gho_|glpat-|xox[baprs]-)[A-Za-z0-9_=-]{12,}"),
)


def redact_text(text: str, *, patterns: Iterable[Pattern[str]] = DEFAULT_PATTERNS) -> str:
    try:
        redacted = text
        for pattern in patterns:
            redacted = pattern.sub("[REDACTED:SECRET]", redacted)
        return redacted
    except Exception as exc:
        raise RedactionError("redaction failed; output suppressed") from exc


def redact_exception(exc: BaseException) -> RuntimeError:
    return RuntimeError(redact_text(str(exc)))
