from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.knowledge.retrieval import KnowledgeRetriever
from se_mentor.models.knowledge import KnowledgeStatus, KnowledgeType


def test_T035_direct_path_verified_knowledge_ranks_before_stale_keyword_match(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "knowledge-retrieval.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other_ids = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        repo = KnowledgeRepository(session)
        repo.add(
            project_id=ids["project_id"],
            key="migration-linear",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.VERIFIED,
            scope_paths=("backend/migrations/env.py",),
            summary="Alembic migrations must remain linear.",
            evidence_refs=("evidence://T016",),
        )
        repo.add(
            project_id=ids["project_id"],
            key="stale-keyword",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.STALE,
            scope_paths=("backend/legacy.py",),
            summary="Alembic legacy keyword match.",
            evidence_refs=("evidence://old",),
        )
        repo.add(
            project_id=ids["project_id"],
            key="failed-experience",
            knowledge_type=KnowledgeType.FAILURE,
            status=KnowledgeStatus.FAILED_EXPERIENCE,
            scope_paths=("backend/migrations/env.py",),
            summary="A failed migration attempt caused rollback.",
            evidence_refs=("evidence://failed",),
        )
        repo.add(
            project_id=other_ids["project_id"],
            key="other-project",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.VERIFIED,
            scope_paths=("backend/migrations/env.py",),
            summary="Other project knowledge must not leak.",
            evidence_refs=("evidence://other",),
        )

        retriever = KnowledgeRetriever(session)
        first = retriever.search(
            project_id=ids["project_id"],
            paths=("backend/migrations/env.py",),
            keywords=("Alembic",),
        )
        second = retriever.search(
            project_id=ids["project_id"],
            paths=("backend/migrations/env.py",),
            keywords=("Alembic",),
        )
        other = retriever.search(
            project_id=other_ids["project_id"],
            paths=("backend/unknown.py",),
            keywords=("missing",),
        )

    assert [hit.knowledge_key for hit in first] == [hit.knowledge_key for hit in second]
    assert first[0].knowledge_key == "migration-linear"
    assert "direct path" in first[0].reasons
    assert "verified" in first[0].reasons
    assert first[0].can_inform_success is True
    failed = next(hit for hit in first if hit.knowledge_key == "failed-experience")
    assert failed.can_inform_success is False
    assert first.index(failed) < first.index(
        next(hit for hit in first if hit.knowledge_key == "stale-keyword")
    )
    assert other == ()
