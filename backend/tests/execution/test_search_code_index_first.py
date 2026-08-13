from __future__ import annotations

import subprocess
from pathlib import Path

from phase1_test_helpers import create_schema

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.execution import orchestrator
from se_mentor.models.code_index import CodeIndex, CodeIndexStatus, CodeSymbol, CodeSymbolKind
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask, TaskStatus


def test_search_code_uses_code_index_before_filesystem(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def target_function():\n    return True\n", encoding="utf-8")
    engine = create_schema(tmp_path / "search-index.sqlite3")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="change target function",
            base_revision="rev-1",
            status=TaskStatus.EXECUTING,
        )
        session.add(task)
        index = CodeIndex(
            project_id=project.id,
            revision="rev-1",
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json="{}",
        )
        session.add(index)
        session.flush()
        session.add(
            CodeSymbol(
                code_index_id=index.id,
                project_id=project.id,
                revision="rev-1",
                symbol_key="app:target_function",
                qualified_name="app.target_function",
                kind=CodeSymbolKind.FUNCTION,
                relative_path="app.py",
                signature_hash="a" * 64,
            )
        )
        session.flush()

        def fail_rglob(*_args, **_kwargs):
            raise AssertionError("SEARCH_CODE must not scan filesystem when index matches")

        monkeypatch.setattr(Path, "rglob", fail_rglob)
        result = orchestrator._search_code(
            session,
            task,
            repo,
            "target_function",
            revision="rev-1",
        )

    assert result["source"] == "code_index"
    assert result["matches"][0]["path"] == "app.py"


def test_search_code_uses_tracked_files_without_recursive_filesystem_scan(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    frontend = repo / "frontend" / "src" / "app"
    frontend.mkdir(parents=True)
    (frontend / "fixtures.ts").write_text(
        "export const nav = [{ label: '任务' }]\n",
        encoding="utf-8",
    )
    ignored = repo / "node_modules" / "pkg"
    ignored.mkdir(parents=True)
    (ignored / "bad.ts").write_text("任务\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo, check=True)
    subprocess.run(["git", "add", "frontend/src/app/fixtures.ts"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    engine = create_schema(tmp_path / "search-tracked.sqlite3")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="change task label",
            base_revision="rev-1",
            status=TaskStatus.EXECUTING,
        )
        session.add(task)
        session.flush()

        def fail_rglob(*_args, **_kwargs):
            raise AssertionError("SEARCH_CODE fallback must not call Path.rglob")

        monkeypatch.setattr(Path, "rglob", fail_rglob)
        result = orchestrator._search_code(session, task, repo, "任务", revision="rev-1")

    assert result["source"] == "tracked_files"
    assert result["matches"][0]["path"] == "frontend/src/app/fixtures.ts"
    assert result["total_matches"] == 1


def test_search_code_non_git_fallback_is_bounded_and_exclusion_aware(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    target_dir = repo / "frontend" / "src"
    target_dir.mkdir(parents=True)
    (target_dir / "copy.tsx").write_text("<h1>UI</h1>\n", encoding="utf-8")
    hidden_dir = repo / ".tmp"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "copy.tsx").write_text("<h1>UI</h1>\n", encoding="utf-8")
    engine = create_schema(tmp_path / "search-bounded.sqlite3")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="change UI",
            base_revision="rev-1",
            status=TaskStatus.EXECUTING,
        )
        session.add(task)
        session.flush()

        def fail_rglob(*_args, **_kwargs):
            raise AssertionError("bounded fallback must not call Path.rglob")

        monkeypatch.setattr(Path, "rglob", fail_rglob)
        result = orchestrator._search_code(session, task, repo, "UI", revision="rev-1")

    assert result["source"] == "filesystem_bounded"
    assert result["matches"][0]["path"] == "frontend/src/copy.tsx"
