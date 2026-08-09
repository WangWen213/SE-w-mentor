from __future__ import annotations

import json
import re
from collections.abc import Iterable

from sqlalchemy.orm import Session

from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)

_SENSITIVE_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*=\s*[^,\s;]+")


class KnowledgeCandidateExtractor:
    def __init__(self, session: Session) -> None:
        self.session = session

    def from_llm_summary(
        self,
        *,
        project_id: str,
        task_id: str,
        knowledge_key: str,
        knowledge_type: KnowledgeType,
        summary: str,
        scope_paths: Iterable[str],
        source_ref: str,
        rollback_task: bool = False,
    ) -> EngineeringKnowledge:
        status = KnowledgeStatus.FAILED_EXPERIENCE if rollback_task else KnowledgeStatus.CANDIDATE
        knowledge = EngineeringKnowledge(
            project_id=project_id,
            knowledge_key=knowledge_key,
            knowledge_type=knowledge_type,
            status=status,
            version=1,
            scope_json=json.dumps(tuple(scope_paths), sort_keys=True),
            summary=_redact_sensitive(summary),
            verified_evidence_json=None,
        )
        self.session.add(knowledge)
        self.session.flush()
        self.session.add(
            KnowledgeSource(
                knowledge_id=knowledge.id,
                source_type=KnowledgeSourceType.LLM_SUMMARY,
                source_ref=source_ref,
                evidence_json=json.dumps({"task_id": task_id, "source_ref": source_ref}),
            )
        )
        self.session.flush()
        return knowledge


def _redact_sensitive(value: str) -> str:
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
