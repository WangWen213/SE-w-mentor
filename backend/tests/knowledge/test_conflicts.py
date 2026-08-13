from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.conflicts import ConflictDecision, KnowledgeConflictService
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeRelation,
    KnowledgeRelationType,
    KnowledgeStatus,
    KnowledgeType,
)


def test_T038_conflicting_new_knowledge_does_not_overwrite_old_record(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "conflicts.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        repo = KnowledgeRepository(session)
        old = repo.add(
            project_id=ids["project_id"],
            key="cache-policy",
            knowledge_type=KnowledgeType.CONSTRAINT,
            status=KnowledgeStatus.VERIFIED,
            scope_paths=("backend/cache.py",),
            summary="Cache writes require a transaction.",
            evidence_refs=("evidence://old",),
        )
        new = repo.add(
            project_id=ids["project_id"],
            key="cache-policy",
            knowledge_type=KnowledgeType.CONSTRAINT,
            status=KnowledgeStatus.CANDIDATE,
            scope_paths=("backend/cache.py",),
            summary="Cache writes may skip transactions.",
            evidence_refs=("evidence://new",),
            version=2,
        )
        service = KnowledgeConflictService(session)
        decision = service.evaluate_candidate(new.id)

        stored_old = session.get(EngineeringKnowledge, old.id)
        stored_new = session.get(EngineeringKnowledge, new.id)
        relations = session.query(KnowledgeRelation).all()

    assert decision is ConflictDecision.CONSERVATIVE_GOVERNANCE_REQUIRED
    assert stored_old is not None
    assert stored_new is not None
    assert stored_old.summary == "Cache writes require a transaction."
    assert stored_old.status == KnowledgeStatus.VERIFIED
    assert stored_new.status == KnowledgeStatus.CONFLICTING
    assert len(relations) == 1
    assert relations[0].relation_type == KnowledgeRelationType.CONFLICTS_WITH
    assert relations[0].source_knowledge_id == new.id
    assert relations[0].target_knowledge_id == old.id
