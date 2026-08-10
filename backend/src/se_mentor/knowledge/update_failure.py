from __future__ import annotations

import re
from dataclasses import dataclass

from se_mentor.models.knowledge import KnowledgeStatus, KnowledgeType
from se_mentor.security.redaction import redact_text


@dataclass(frozen=True)
class FailedTaskResult:
    task_id: str
    outcome: str
    attempted_paths: tuple[str, ...]
    failure_summary: str
    evidence_refs: tuple[str, ...]
    log_text: str


@dataclass(frozen=True)
class FailureKnowledgeRecord:
    task_id: str
    knowledge_type: KnowledgeType
    status: KnowledgeStatus
    outcome: str
    attempted_paths: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    summary: str
    active_implementation_fact: bool


class FailureKnowledgeUpdater:
    def extract(self, result: FailedTaskResult) -> FailureKnowledgeRecord:
        summary = "\n".join(
            part
            for part in (
                result.outcome,
                _redact_failure_text(result.failure_summary),
                _redact_failure_text(result.log_text),
            )
            if part.strip()
        )
        return FailureKnowledgeRecord(
            task_id=result.task_id,
            knowledge_type=KnowledgeType.FAILURE,
            status=KnowledgeStatus.FAILED_EXPERIENCE,
            outcome=result.outcome,
            attempted_paths=tuple(path.replace("\\", "/") for path in result.attempted_paths),
            evidence_refs=tuple(ref for ref in result.evidence_refs if ref.strip()),
            summary=summary,
            active_implementation_fact=False,
        )


def _redact_failure_text(text: str) -> str:
    redacted = redact_text(text)
    return re.sub(
        r"(?i)\b[\w-]*(?:api[_-]?key|token|secret|password)=[^\s]+",
        "[REDACTED:SECRET]",
        redacted,
    )
