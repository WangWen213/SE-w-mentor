from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, execute, seed_task_graph
from sqlalchemy import exc

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeRelation,
    KnowledgeRelationType,
    KnowledgeSignature,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)


def test_T016_unverified_llm_summary_cannot_be_verified_without_evidence(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "knowledge.sqlite3")
    ids = seed_task_graph(engine, tmp_path)

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO engineering_knowledge (
                id, project_id, knowledge_key, knowledge_type, status, version,
                scope_json, summary, verified_evidence_json, created_at
            )
            VALUES (
                'bad-verified', :project_id, 'llm-summary', 'PATTERN', 'VERIFIED',
                1, '[]', 'LLM summary without evidence', NULL, CURRENT_TIMESTAMP
            )
            """,
            {"project_id": ids["project_id"]},
        )


def test_T016_sources_signatures_relations_and_project_boundary(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "knowledge-relations.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other_ids = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        knowledge = EngineeringKnowledge(
            project_id=ids["project_id"],
            knowledge_key="safe-migration",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.VERIFIED,
            version=1,
            scope_json='["backend/migrations"]',
            summary="Migrations stay linear.",
            verified_evidence_json='[{"source":"tests","summary":"passed"}]',
        )
        replacement = EngineeringKnowledge(
            project_id=ids["project_id"],
            knowledge_key="safe-migration",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.CANDIDATE,
            version=2,
            scope_json='["backend/migrations"]',
            summary="Updated migration guidance.",
        )
        other = EngineeringKnowledge(
            project_id=other_ids["project_id"],
            knowledge_key="other-project",
            knowledge_type=KnowledgeType.PATTERN,
            status=KnowledgeStatus.CANDIDATE,
            version=1,
            scope_json="[]",
            summary="Other project.",
        )
        session.add_all([knowledge, replacement, other])
        session.flush()
        session.add(KnowledgeSignature(knowledge_id=knowledge.id, signature_hash="a" * 64))
        session.add(
            KnowledgeSource(
                knowledge_id=knowledge.id,
                source_type=KnowledgeSourceType.TEST,
                source_ref="evidence://T016",
                evidence_json='[{"source":"pytest","summary":"passed"}]',
            )
        )
        session.add(
            KnowledgeRelation(
                project_id=ids["project_id"],
                source_knowledge_id=replacement.id,
                target_knowledge_id=knowledge.id,
                relation_type=KnowledgeRelationType.SUPERSEDES,
                evidence_json='[{"source":"T016","summary":"explicit history"}]',
            )
        )
        session.flush()
        other_id = other.id
        replacement_id = replacement.id

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO knowledge_relations (
                id, project_id, source_knowledge_id, target_knowledge_id,
                relation_type, evidence_json, created_at
            )
            VALUES (
                'bad-cross-project', :project_id, :source_id, :target_id,
                'CONFLICTS_WITH', '[]', CURRENT_TIMESTAMP
            )
            """,
            {
                "project_id": ids["project_id"],
                "source_id": replacement_id,
                "target_id": other_id,
            },
        )
