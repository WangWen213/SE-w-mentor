from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.indexing.python_indexer import PythonIndexer
from se_mentor.indexing.relation_extractor import RelationExtractor
from se_mentor.models.code_index import CodeSymbolRelation, CodeSymbolRelationType


def test_T031_direct_import_call_and_test_edges_are_created_without_false_cross_project_edges(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "relations.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "import json\n\n"
        "def encode(value):\n"
        "    return json.dumps(value)\n\n"
        "def read_users(db):\n"
        "    db.execute('SELECT * FROM users')\n\n"
        "def write_users(db):\n"
        "    db.execute('INSERT INTO users VALUES (1)')\n",
        encoding="utf-8",
    )
    (repo / "test_service.py").write_text(
        "from service import encode\n\ndef test_encode():\n    assert encode({'a': 1})\n",
        encoding="utf-8",
    )

    with session_scope(session_factory) as session:
        PythonIndexer(session).build(ids["project_id"], repo, "rev1")
        extractor = RelationExtractor(session)
        result = extractor.extract(ids["project_id"], repo, "rev1")
        PythonIndexer(session).build(other["project_id"], repo, "rev1")

    assert result.unresolved_edges
    with session_scope(session_factory) as session:
        relations = session.query(CodeSymbolRelation).all()
        relation_types = {relation.relation_type for relation in relations}
        assert CodeSymbolRelationType.IMPORTS in relation_types
        assert CodeSymbolRelationType.CALLS in relation_types
        assert CodeSymbolRelationType.TESTS in relation_types
        assert CodeSymbolRelationType.SERIALIZES in relation_types
        assert CodeSymbolRelationType.READS_TABLE in relation_types
        assert CodeSymbolRelationType.WRITES_TABLE in relation_types
        assert all(relation.source_project_id == ids["project_id"] for relation in relations)
        assert extractor.related_symbols(relations[0].source_symbol_id, depth=2)
