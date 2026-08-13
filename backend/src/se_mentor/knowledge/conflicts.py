from __future__ import annotations

import json
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeRelation,
    KnowledgeRelationType,
    KnowledgeStatus,
)


class ConflictDecision(StrEnum):
    NO_CONFLICT = "NO_CONFLICT"
    CONSERVATIVE_GOVERNANCE_REQUIRED = "CONSERVATIVE_GOVERNANCE_REQUIRED"


class KnowledgeConflictService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate_candidate(self, candidate_id: str) -> ConflictDecision:
        candidate = self.session.get(EngineeringKnowledge, candidate_id)
        if candidate is None:
            raise ValueError("candidate knowledge not found")
        existing = self.session.scalars(
            select(EngineeringKnowledge).where(
                EngineeringKnowledge.project_id == candidate.project_id,
                EngineeringKnowledge.knowledge_key == candidate.knowledge_key,
                EngineeringKnowledge.id != candidate.id,
            )
        ).all()
        for old in existing:
            if _same_scope(old, candidate) and old.summary.strip() != candidate.summary.strip():
                candidate.status = KnowledgeStatus.CONFLICTING
                self._add_conflict(candidate, old)
                self.session.flush()
                return ConflictDecision.CONSERVATIVE_GOVERNANCE_REQUIRED
        return ConflictDecision.NO_CONFLICT

    def _add_conflict(
        self,
        candidate: EngineeringKnowledge,
        old: EngineeringKnowledge,
    ) -> None:
        existing = self.session.scalar(
            select(KnowledgeRelation).where(
                KnowledgeRelation.source_knowledge_id == candidate.id,
                KnowledgeRelation.target_knowledge_id == old.id,
                KnowledgeRelation.relation_type == KnowledgeRelationType.CONFLICTS_WITH,
            )
        )
        if existing is not None:
            return
        self.session.add(
            KnowledgeRelation(
                project_id=candidate.project_id,
                source_knowledge_id=candidate.id,
                target_knowledge_id=old.id,
                relation_type=KnowledgeRelationType.CONFLICTS_WITH,
                evidence_json=json.dumps(
                    {
                        "candidate": candidate.knowledge_key,
                        "old_version": old.version,
                        "candidate_version": candidate.version,
                        "governance": "WARN_OR_BLOCK",
                    },
                    sort_keys=True,
                ),
            )
        )


def _same_scope(left: EngineeringKnowledge, right: EngineeringKnowledge) -> bool:
    return left.scope_json == right.scope_json
