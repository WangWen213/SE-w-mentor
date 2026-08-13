from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.extractor import KnowledgeCandidateExtractor
from se_mentor.knowledge.promotion import KnowledgePromotionService, PromotionDecision
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)


def test_T039_llm_candidate_without_evidence_cannot_be_verified(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "promotion.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        extractor = KnowledgeCandidateExtractor(session)
        candidate = extractor.from_llm_summary(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            knowledge_key="audit-pattern",
            knowledge_type=KnowledgeType.PATTERN,
            summary="Persist audit events through AuditLogRepository. api_key=secret-123",
            scope_paths=("backend/src/se_mentor/audit.py",),
            source_ref="llm-call://t039",
        )
        rollback = extractor.from_llm_summary(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            knowledge_key="rollback-fact",
            knowledge_type=KnowledgeType.DECISION,
            summary="Rollback deleted the audit table.",
            scope_paths=("backend/src/se_mentor/audit.py",),
            source_ref="llm-call://rollback",
            rollback_task=True,
        )
        service = KnowledgePromotionService(session)
        no_evidence = service.promote(candidate.id)
        verified = service.promote(
            candidate.id,
            evidence_refs=("pytest://backend/tests/test_audit.py::test_audit_logs",),
            source_type=KnowledgeSourceType.TEST,
        )
        human = extractor.from_llm_summary(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            knowledge_key="reviewed-pattern",
            knowledge_type=KnowledgeType.CONSTRAINT,
            summary="User confirmed audit records are append-only.",
            scope_paths=("backend/src/se_mentor/audit.py",),
            source_ref="llm-call://reviewed",
        )
        reviewed = service.promote(
            human.id,
            evidence_refs=("review://user-1",),
            source_type=KnowledgeSourceType.USER_REVIEW,
        )
        stored = session.get(EngineeringKnowledge, candidate.id)
        sources = (
            session.query(KnowledgeSource)
            .filter(KnowledgeSource.knowledge_id == candidate.id)
            .order_by(KnowledgeSource.source_type, KnowledgeSource.source_ref)
            .all()
        )

    assert no_evidence is PromotionDecision.NEEDS_EVIDENCE
    assert verified is PromotionDecision.VERIFIED
    assert reviewed is PromotionDecision.REVIEWED
    assert stored is not None
    assert stored.status == KnowledgeStatus.VERIFIED
    assert "secret-123" not in stored.summary
    assert rollback.status == KnowledgeStatus.FAILED_EXPERIENCE
    assert rollback.verified_evidence_json is None
    assert [source.source_type for source in sources] == [
        KnowledgeSourceType.LLM_SUMMARY,
        KnowledgeSourceType.TEST,
    ]
