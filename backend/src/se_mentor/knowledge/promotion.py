from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy.orm import Session

from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
)


class PromotionDecision(StrEnum):
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    VERIFIED = "VERIFIED"
    REVIEWED = "REVIEWED"


class KnowledgePromotionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def promote(
        self,
        knowledge_id: str,
        *,
        evidence_refs: Iterable[str] = (),
        source_type: KnowledgeSourceType = KnowledgeSourceType.TEST,
    ) -> PromotionDecision:
        knowledge = self.session.get(EngineeringKnowledge, knowledge_id)
        if knowledge is None:
            raise ValueError("knowledge not found")
        evidence = tuple(ref for ref in evidence_refs if ref.strip())
        if not evidence:
            self.session.flush()
            return PromotionDecision.NEEDS_EVIDENCE
        for ref in evidence:
            self.session.add(
                KnowledgeSource(
                    knowledge_id=knowledge.id,
                    source_type=source_type,
                    source_ref=ref,
                    evidence_json=json.dumps({"source_ref": ref}),
                )
            )
        knowledge.verified_evidence_json = json.dumps(evidence, sort_keys=True)
        if source_type == KnowledgeSourceType.USER_REVIEW:
            knowledge.status = KnowledgeStatus.REVIEWED
            decision = PromotionDecision.REVIEWED
        else:
            knowledge.status = KnowledgeStatus.VERIFIED
            decision = PromotionDecision.VERIFIED
        self.session.flush()
        return decision
