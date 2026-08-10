from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.contracts.enums import FeedbackKind, FeedbackSeverity
from se_mentor.contracts.feedback import FeedbackSignal as ContractFeedbackSignal
from se_mentor.models.validation import FeedbackSignal
from se_mentor.security.redaction import redact_text


@dataclass(frozen=True)
class FeedbackSource:
    source_type: str
    category: str
    retryable: bool
    log_text: str
    artifact_ref: str


class FeedbackController:
    def __init__(self, session: Session, *, max_chars: int = 600) -> None:
        self.session = session
        self.max_chars = max_chars

    def create(self, *, task_id: str, source: FeedbackSource) -> ContractFeedbackSignal:
        message = self._message(source)
        kind = _kind(source.source_type)
        severity = FeedbackSeverity.ERROR if source.category else FeedbackSeverity.WARNING
        self.session.add(
            FeedbackSignal(
                task_id=task_id,
                kind=kind,
                severity=severity,
                summary=message,
                evidence_json=json.dumps(
                    {
                        "artifact_ref": source.artifact_ref,
                        "source_type": source.source_type,
                        "category": source.category,
                    },
                    sort_keys=True,
                ),
            )
        )
        self.session.flush()
        return ContractFeedbackSignal(kind=kind, severity=severity, message=message)

    def _message(self, source: FeedbackSource) -> str:
        redacted = redact_text(source.log_text)
        facts = [
            f"{source.source_type}:{source.category}",
            "retryable" if source.retryable else "not retryable",
        ]
        facts.extend(_actionable_lines(redacted))
        message = "\n".join(dict.fromkeys(facts))
        if len(message) <= self.max_chars:
            return message
        return message[: self.max_chars - 13].rstrip() + "\n[truncated]"


def _kind(source_type: str) -> FeedbackKind:
    if source_type.lower() == "validation":
        return FeedbackKind.VALIDATION
    if source_type.lower() == "governance":
        return FeedbackKind.GOVERNANCE
    if source_type.lower() == "progress":
        return FeedbackKind.PROGRESS
    return FeedbackKind.TOOL


def _actionable_lines(text: str) -> list[str]:
    actionable: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if (
            "FAILED" in stripped
            or "AssertionError" in stripped
            or "[REDACTED:SECRET]" in stripped
            or re.search(r"\b[\w./-]+::[\w.-]+", stripped)
        ):
            actionable.append(stripped)
        if len(actionable) >= 6:
            break
    return actionable
