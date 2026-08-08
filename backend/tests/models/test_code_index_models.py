from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import REVISION, create_schema, execute, seed_task_graph
from sqlalchemy import exc

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.code_index import (
    CodeIndex,
    CodeIndexStatus,
    CodeSymbol,
    CodeSymbolKind,
    CodeSymbolRelation,
    CodeSymbolRelationType,
)


def test_T017_symbol_relation_cannot_cross_project_or_revision(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "code-index.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other_ids = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        index = CodeIndex(
            project_id=ids["project_id"],
            revision=REVISION,
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json='[{"source":"T017","summary":"index"}]',
        )
        other_index = CodeIndex(
            project_id=other_ids["project_id"],
            revision=REVISION,
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json="[]",
        )
        session.add_all([index, other_index])
        session.flush()
        source = CodeSymbol(
            code_index_id=index.id,
            project_id=ids["project_id"],
            revision=REVISION,
            symbol_key="pkg.module:func",
            qualified_name="pkg.module.func",
            kind=CodeSymbolKind.FUNCTION,
            relative_path="pkg/module.py",
        )
        target = CodeSymbol(
            code_index_id=other_index.id,
            project_id=other_ids["project_id"],
            revision=REVISION,
            symbol_key="pkg.other:func",
            qualified_name="pkg.other.func",
            kind=CodeSymbolKind.FUNCTION,
            relative_path="pkg/other.py",
        )
        session.add_all([source, target])
        session.flush()
        source_id = source.id
        target_id = target.id

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO code_symbol_relations (
                id, source_symbol_id, source_project_id, source_revision,
                target_symbol_id, target_project_id, target_revision, relation_type,
                evidence_json, created_at
            )
            VALUES (
                'bad-cross-project', :source_id, :source_project_id, :revision,
                :target_id, :target_project_id, :revision, 'CALLS', '[]',
                CURRENT_TIMESTAMP
            )
            """,
            {
                "source_id": source_id,
                "source_project_id": ids["project_id"],
                "target_id": target_id,
                "target_project_id": other_ids["project_id"],
                "revision": REVISION,
            },
        )


def test_T017_index_identity_symbol_uniqueness_and_relation_types(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "code-index-ok.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        index = CodeIndex(
            project_id=ids["project_id"],
            revision=REVISION,
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json="[]",
        )
        session.add(index)
        session.flush()
        source = CodeSymbol(
            code_index_id=index.id,
            project_id=ids["project_id"],
            revision=REVISION,
            symbol_key="pkg.module:func",
            qualified_name="pkg.module.func",
            kind=CodeSymbolKind.FUNCTION,
            relative_path="pkg/module.py",
        )
        target = CodeSymbol(
            code_index_id=index.id,
            project_id=ids["project_id"],
            revision=REVISION,
            symbol_key="pkg.module:Test",
            qualified_name="pkg.module.Test",
            kind=CodeSymbolKind.TEST,
            relative_path="pkg/test_module.py",
        )
        session.add_all([source, target])
        session.flush()
        session.add(
            CodeSymbolRelation(
                source_symbol_id=target.id,
                source_project_id=ids["project_id"],
                source_revision=REVISION,
                target_symbol_id=source.id,
                target_project_id=ids["project_id"],
                target_revision=REVISION,
                relation_type=CodeSymbolRelationType.TESTS,
                evidence_json='[{"source":"T017","summary":"relation"}]',
            )
        )
        session.flush()

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO code_indexes (
                id, project_id, revision, language, status, index_generation,
                evidence_json, created_at, updated_at
            )
            VALUES (
                'duplicate-index', :project_id, :revision, 'python', 'READY',
                2, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"project_id": ids["project_id"], "revision": REVISION},
        )
