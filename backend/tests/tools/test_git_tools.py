from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.contracts.enums import ToolStatus
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.execution import ToolExecution
from se_mentor.tools.dispatcher import ToolDispatcher
from se_mentor.tools.git_tools import GitToolError, ReadOnlyGitTools, register_read_only_git_tools
from se_mentor.tools.registry import ToolRegistry


def test_T063_git_tool_has_no_commit_push_or_write_side_effect(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "git-tools.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    before_head = _git(repo, "rev-parse", "HEAD")
    before_index = _git(repo, "ls-files", "-s")
    before_status = _git(repo, "status", "--porcelain=v1")
    registry = ToolRegistry()
    register_read_only_git_tools(registry)
    tools = ReadOnlyGitTools(repo)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        dispatcher = ToolDispatcher(session, registry)
        status_result = dispatcher.dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="git_status",
            parameters={"pathspec": "app.py"},
            enforcer=lambda: True,
            handler=lambda: tools.status(pathspec=("app.py",)),
        )
        revision_result = dispatcher.dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="git_revision",
            parameters={},
            enforcer=lambda: True,
            handler=tools.revision,
        )
        with pytest.raises(GitToolError, match="pathspec"):
            tools.diff(pathspec=("../outside.py",))
        executions = session.query(ToolExecution).all()

    assert status_result.status == ToolStatus.OK
    assert revision_result.status == ToolStatus.OK
    assert registry.get("git_commit") is None
    assert registry.get("git_push") is None
    assert _git(repo, "rev-parse", "HEAD") == before_head
    assert _git(repo, "ls-files", "-s") == before_index
    assert _git(repo, "status", "--porcelain=v1") == before_status
    assert len(executions) == 2


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
