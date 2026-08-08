from __future__ import annotations

import subprocess
from os.path import normcase
from pathlib import Path

import pytest
from phase1_test_helpers import create_schema

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.project import Project
from se_mentor.projects.project_service import ProjectRegistrationError, register_project


def _git_repo(path: Path) -> str:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_AC_FR01_01_rejects_non_git_outside_and_duplicate_project(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "project.sqlite3")
    session_factory = create_session_factory(engine)
    allowed = tmp_path / "allowed"
    repo = allowed / "repo"
    head = _git_repo(repo)

    before_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout

    with session_scope(session_factory) as session:
        registered = register_project(session, repo, authorized_root=allowed)
        assert registered.current_revision == head
        assert registered.project.normalized_root_path == normcase(str(repo.resolve()))

    after_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert after_status == before_status

    with (
        session_scope(session_factory) as session,
        pytest.raises(ProjectRegistrationError, match="duplicate"),
    ):
        register_project(session, repo, authorized_root=allowed)

    with session_scope(session_factory) as session:
        (allowed / "not-git").mkdir()
        with pytest.raises(ProjectRegistrationError, match="Git"):
            register_project(session, allowed / "not-git", authorized_root=allowed)

    outside = tmp_path / "outside"
    _git_repo(outside)
    with (
        session_scope(session_factory) as session,
        pytest.raises(ProjectRegistrationError, match="authorized"),
    ):
        register_project(session, outside, authorized_root=allowed)

    escape_link = allowed / "escape-link"
    try:
        escape_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available in this environment")
    with (
        session_scope(session_factory) as session,
        pytest.raises(ProjectRegistrationError, match="authorized"),
    ):
        register_project(session, escape_link, authorized_root=allowed)

    with session_scope(session_factory) as session:
        assert session.query(Project).count() == 1
