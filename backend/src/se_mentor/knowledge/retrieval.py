from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeStatus


@dataclass(frozen=True)
class KnowledgeHit:
    knowledge_id: str
    knowledge_key: str
    score: int
    reasons: tuple[str, ...]
    can_inform_success: bool


class KnowledgeRetriever:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        *,
        project_id: str,
        paths: tuple[str, ...] = (),
        keywords: tuple[str, ...] = (),
        limit: int = 20,
    ) -> tuple[KnowledgeHit, ...]:
        rows = self.session.scalars(
            select(EngineeringKnowledge).where(EngineeringKnowledge.project_id == project_id)
        ).all()
        hits = [self._score(row, paths, keywords) for row in rows]
        matched = [hit for hit in hits if hit.score > 0]
        return tuple(
            sorted(matched, key=lambda hit: (-hit.score, hit.knowledge_key, hit.knowledge_id))[:limit]
        )

    def _score(
        self,
        row: EngineeringKnowledge,
        paths: tuple[str, ...],
        keywords: tuple[str, ...],
    ) -> KnowledgeHit:
        reasons: list[str] = []
        score = 0
        scope = _scope(row.scope_json)
        if any(path in scope for path in paths):
            score += 80
            reasons.append("direct path")
        lowered = row.summary.lower()
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in lowered]
        if matched_keywords:
            score += 20 * len(matched_keywords)
            reasons.append("keyword")
        if score == 0:
            return KnowledgeHit(
                knowledge_id=row.id,
                knowledge_key=row.knowledge_key,
                score=0,
                reasons=(),
                can_inform_success=False,
            )
        status = KnowledgeStatus(row.status)
        if status == KnowledgeStatus.VERIFIED:
            score += 100
            reasons.append("verified")
        elif status == KnowledgeStatus.REVIEWED:
            score += 70
            reasons.append("reviewed")
        elif status == KnowledgeStatus.STALE:
            score -= 10
            reasons.append("stale")
        elif status == KnowledgeStatus.FAILED_EXPERIENCE:
            score += 10
            reasons.append("failed experience")
        return KnowledgeHit(
            knowledge_id=row.id,
            knowledge_key=row.knowledge_key,
            score=score,
            reasons=tuple(reasons),
            can_inform_success=status
            not in {KnowledgeStatus.FAILED_EXPERIENCE, KnowledgeStatus.STALE},
        )


def _scope(scope_json: str) -> tuple[str, ...]:
    try:
        data = json.loads(scope_json)
    except json.JSONDecodeError:
        return ()
    if isinstance(data, list):
        return tuple(str(item) for item in data)
    return ()
