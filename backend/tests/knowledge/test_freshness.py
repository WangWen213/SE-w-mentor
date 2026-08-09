from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.freshness import FreshnessService, FreshnessStatus
from se_mentor.knowledge.refresh_queue import RefreshQueue
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.knowledge.signature import KnowledgeSignatureBuilder
from se_mentor.models.audit import AlertEvent, AuditEvent
from se_mentor.models.knowledge import KnowledgeSignature, KnowledgeStatus, KnowledgeType


def test_T037_changed_symbol_marks_knowledge_stale_and_blocks_auto_allow(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "freshness.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "service.py"
    target.write_text("def answer():\n    return 1\n", encoding="utf-8")
    builder = KnowledgeSignatureBuilder(repo_root)
    original = builder.for_file("service.py", revision="r1", symbol_name="answer")

    with session_scope(session_factory) as session:
        repo = KnowledgeRepository(session)
        knowledge = repo.add(
            project_id=ids["project_id"],
            key="answer-rule",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.VERIFIED,
            scope_paths=("service.py",),
            summary="answer returns one",
            evidence_refs=("evidence://fresh",),
        )
        session.add(
            KnowledgeSignature(knowledge_id=knowledge.id, signature_hash=original.signature_hash)
        )
        session.flush()
        knowledge_id = knowledge.id

    target.write_text("def answer():\n    return 2\n", encoding="utf-8")
    changed = builder.for_file("service.py", revision="r2", symbol_name="answer")
    queue = RefreshQueue()

    with session_scope(session_factory) as session:
        service = FreshnessService(session, queue)
        result = service.evaluate(knowledge_id, changed.signature_hash)
        repeated = service.evaluate(knowledge_id, changed.signature_hash)
        assert result.status is FreshnessStatus.DRIFTED
        assert repeated.status is FreshnessStatus.STALE
        assert result.can_auto_allow is False
        assert queue.items == (knowledge_id,)
        stored = session.get(type(knowledge), knowledge_id)
        assert stored is not None
        assert stored.status == KnowledgeStatus.STALE
        assert session.query(AuditEvent).count() == 1
        assert session.query(AlertEvent).count() == 1

        missing = service.evaluate("missing-knowledge", changed.signature_hash)
        unknown = service.evaluate(knowledge_id, None)

    assert missing.status is FreshnessStatus.MISSING
    assert unknown.status is FreshnessStatus.UNKNOWN
