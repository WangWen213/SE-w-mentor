from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.impact.direct import DirectImpactAnalyzer, DirectImpactKind
from se_mentor.indexing.python_indexer import PythonIndexer


def test_T040_field_change_identifies_direct_dto_api_table_and_test_evidence(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "direct-impact.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    source = repo / "backend" / "src" / "app"
    tests = repo / "backend" / "tests"
    source.mkdir(parents=True)
    tests.mkdir(parents=True)
    api_path = source / "api.py"
    api_path.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                "",
                "class UserDTO:",
                "    name: str",
                "",
                "@router.get('/users/{user_id}')",
                "def get_user(user_id: str):",
                "    return db.execute('SELECT name FROM users WHERE id = ?', user_id)",
            ]
        ),
        encoding="utf-8",
    )
    (tests / "test_api.py").write_text(
        "from backend.src.app.api import get_user\n\n"
        "def test_get_user():\n"
        "    assert get_user('1') is not None\n",
        encoding="utf-8",
    )
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        PythonIndexer(session).build(ids["project_id"], repo, REVISION)
        result = DirectImpactAnalyzer(session).analyze(
            project_id=ids["project_id"],
            revision=REVISION,
            proposal_scope=("backend/src/app/api.py",),
            diff_text=(
                "diff --git a/backend/src/app/api.py b/backend/src/app/api.py\n"
                "+++ b/backend/src/app/api.py\n"
                "@@\n"
                "+    email: str\n"
            ),
        )

    by_kind = {impact.kind: impact for impact in result.impacts}
    assert set(by_kind) == {
        DirectImpactKind.API,
        DirectImpactKind.DTO,
        DirectImpactKind.TABLE,
        DirectImpactKind.TEST,
    }
    assert by_kind[DirectImpactKind.DTO].symbol_name.endswith("UserDTO")
    assert by_kind[DirectImpactKind.API].symbol_name.endswith("get_user")
    assert by_kind[DirectImpactKind.TABLE].symbol_name == "users"
    assert by_kind[DirectImpactKind.TEST].relative_path == "backend/tests/test_api.py"
    assert all(impact.confidence == "confirmed" for impact in result.impacts)
    assert all(impact.evidence_refs for impact in result.impacts)
    assert result.unknowns == ()
