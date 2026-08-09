from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from se_mentor.security.redaction import redact_text


class TrustBoundaryLabel(StrEnum):
    UNTRUSTED_DATA = "UNTRUSTED_DATA"


@dataclass(frozen=True)
class IsolatedRepositoryText:
    source_ref: str
    text: str
    label: TrustBoundaryLabel
    risk_events: tuple[str, ...]
    policy_grants: tuple[str, ...]


class PromptBoundary:
    def isolate_repository_text(self, source_ref: str, text: str) -> IsolatedRepositoryText:
        redacted = _redact_repository_text(text)
        return IsolatedRepositoryText(
            source_ref=source_ref,
            text=redacted,
            label=TrustBoundaryLabel.UNTRUSTED_DATA,
            risk_events=_risk_events(text),
            policy_grants=(),
        )


def _risk_events(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    events: list[str] = []
    if "ignore previous instructions" in lowered or "system prompt" in lowered:
        events.append("instruction_override")
    if "grant shell" in lowered or "shell access" in lowered or "reveal secret" in lowered:
        events.append("privilege_escalation")
    return tuple(events)


def _redact_repository_text(text: str) -> str:
    redacted = redact_text(text)
    return re.sub(r"sk-proj[_-][A-Za-z0-9_-]{16,}", "[REDACTED:SECRET]", redacted)
