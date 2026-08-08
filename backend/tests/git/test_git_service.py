from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from se_mentor.git.git_service import GitService


def _repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "app.py").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)


def test_T032_preserves_preexisting_changes_and_detects_external_modification(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    (repo / "app.py").write_text("one\nuser change\n", encoding="utf-8")
    (repo / "notes.txt").write_text("pre-existing\n", encoding="utf-8")
    service = GitService(repo)

    snapshot = service.capture_task_baseline()
    assert "app.py" in snapshot.preexisting_changes
    assert "notes.txt" in snapshot.preexisting_changes

    service.record_agent_write("app.py")
    (repo / "app.py").write_text("one\nagent change\n", encoding="utf-8")
    (repo / "notes.txt").write_text("external change\n", encoding="utf-8")

    changes = service.detect_external_modifications(snapshot)
    assert "notes.txt" in changes.external_changes
    assert "app.py" in changes.agent_changes
    assert "notes.txt" in service.status().untracked
    assert "agent change" in service.scoped_diff(["app.py"])
    assert service.file_history("app.py")

    members = set(dir(service))
    assert {"commit", "push", "rebase"}.isdisjoint(members)
    assert "subprocess.run" in inspect.getsource(GitService)
