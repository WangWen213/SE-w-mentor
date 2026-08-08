from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.contracts.enums import EventType
from se_mentor.knowledge.refresh_queue import RefreshQueue
from se_mentor.models.audit import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    AuditActorType,
    AuditEvent,
)
from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeSignature, KnowledgeStatus


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    DRIFTED = "DRIFTED"
    STALE = "STALE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessResult:
    status: FreshnessStatus
    can_auto_allow: bool


class FreshnessService:
    def __init__(self, session: Session, refresh_queue: RefreshQueue) -> None:
        self.session = session
        self.refresh_queue = refresh_queue

    def evaluate(
        self,
        knowledge_id: str,
        current_signature_hash: str | None,
    ) -> FreshnessResult:
        knowledge = self.session.get(EngineeringKnowledge, knowledge_id)
        if knowledge is None:
            return FreshnessResult(FreshnessStatus.MISSING, False)
        if current_signature_hash is None:
            return FreshnessResult(FreshnessStatus.UNKNOWN, False)
        stored = self.session.scalars(
            select(KnowledgeSignature).where(KnowledgeSignature.knowledge_id == knowledge_id)
        ).first()
        if stored is None:
            return FreshnessResult(FreshnessStatus.UNKNOWN, False)
        if KnowledgeStatus(knowledge.status) == KnowledgeStatus.STALE:
            self.refresh_queue.enqueue(knowledge_id)
            return FreshnessResult(FreshnessStatus.STALE, False)
        if stored.signature_hash == current_signature_hash:
            return FreshnessResult(FreshnessStatus.FRESH, True)
        knowledge.status = KnowledgeStatus.STALE
        self.refresh_queue.enqueue(knowledge_id)
        self._emit_stale_events(knowledge)
        self.session.flush()
        return FreshnessResult(FreshnessStatus.DRIFTED, False)

    def _emit_stale_events(self, knowledge: EngineeringKnowledge) -> None:
        evidence = json.dumps({"knowledge_id": knowledge.id, "knowledge_key": knowledge.knowledge_key})
        self.session.add(
            AuditEvent(
                task_id=None,
                correlation_id=f"knowledge-stale:{knowledge.id}",
                actor_type=AuditActorType.SYSTEM,
                actor_id="freshness-service",
                event_type=EventType.TOOL_EXECUTED,
                payload_summary="knowledge marked stale",
                evidence_json=evidence,
            )
        )
        self.session.add(
            AlertEvent(
                task_id=None,
                system_scope=True,
                severity=AlertSeverity.WARNING,
                status=AlertStatus.OPEN,
                summary="knowledge freshness drifted",
                evidence_json=evidence,
            )
        )
