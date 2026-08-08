from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.indexing.python_indexer import PythonIndexer
from se_mentor.models.code_index import CodeIndex, CodeSymbol, CodeSymbolKind


def test_T030_extracts_symbols_api_and_tests_and_handles_syntax_error(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "index.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/items')\n"
        "def list_items():\n"
        "    helper()\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n"
        "def helper():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    (repo / "test_api.py").write_text(
        "from api import helper\n\ndef test_helper():\n    assert helper() == 2\n",
        encoding="utf-8",
    )
    (repo / "bad.py").write_text("def broken(:\n", encoding="utf-8")

    with session_scope(session_factory) as session:
        result = PythonIndexer(session).build(
            project_id=ids["project_id"],
            project_root=repo,
            revision="rev1",
        )
        again = PythonIndexer(session).build(
            project_id=ids["project_id"],
            project_root=repo,
            revision="rev1",
        )
        assert again.index_id == result.index_id

    with session_scope(session_factory) as session:
        assert session.query(CodeIndex).count() == 1
        symbols = session.query(CodeSymbol).all()
        names = {symbol.qualified_name: symbol.kind for symbol in symbols}
        assert names["api"] == CodeSymbolKind.MODULE
        assert names["api.list_items"] == CodeSymbolKind.API
        assert names["api.Service"] == CodeSymbolKind.CLASS
        assert names["api.Service.run"] == CodeSymbolKind.METHOD
        assert names["api.helper"] == CodeSymbolKind.FUNCTION
        assert names["test_api.test_helper"] == CodeSymbolKind.TEST
        assert names["bad"] == CodeSymbolKind.MODULE
        index = session.query(CodeIndex).one()
        assert "SyntaxError" in index.evidence_json
