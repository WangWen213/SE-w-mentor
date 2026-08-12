from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        project_id: str,
        key: str,
        knowledge_type: KnowledgeType,
        status: KnowledgeStatus,
        scope_paths: Iterable[str],
        summary: str,
        evidence_refs: Iterable[str] = (),
        evidence_payloads: Iterable[dict[str, Any]] = (),
        version: int = 1,
        source_type: KnowledgeSourceType = KnowledgeSourceType.TEST,
    ) -> EngineeringKnowledge:
        evidence = tuple(evidence_refs)
        payloads = tuple(evidence_payloads)
        knowledge = EngineeringKnowledge(
            project_id=project_id,
            knowledge_key=key,
            knowledge_type=knowledge_type,
            status=status,
            version=version,
            scope_json=json.dumps(tuple(scope_paths), sort_keys=True),
            summary=summary,
            verified_evidence_json=json.dumps(
                evidence if evidence else payloads,
                sort_keys=True,
                default=str,
            )
            if status == KnowledgeStatus.VERIFIED
            else None,
        )
        self.session.add(knowledge)
        self.session.flush()
        for ref in evidence:
            self.session.add(
                KnowledgeSource(
                    knowledge_id=knowledge.id,
                    source_type=source_type,
                    source_ref=ref,
                    evidence_json=json.dumps({"source_ref": ref}),
                )
            )
        for index, payload in enumerate(payloads, start=1):
            self.session.add(
                KnowledgeSource(
                    knowledge_id=knowledge.id,
                    source_type=source_type,
                    source_ref=f"{key}:evidence:{index}",
                    evidence_json=json.dumps(payload, sort_keys=True, default=str),
                )
            )
        self.session.flush()
        return knowledge
