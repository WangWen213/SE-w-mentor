from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.api import projects as projects_api
from se_mentor.main import create_app
from se_mentor.projects import bootstrap as bootstrap_module


def test_choose_local_success_path_terminates(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.setattr(projects_api, "_choose_directory", lambda: repo)

    response = TestClient(create_app()).post("/api/projects/choose-local")

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["rootPath"] == str(repo)
    assert data["readiness"]["projectUnderstanding"] is True


def test_registered_project_can_reopen(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.setattr(projects_api, "_choose_directory", lambda: repo)
    client = TestClient(create_app())

    first = client.post("/api/projects/choose-local")
    second = client.post("/api/projects/choose-local")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_registered_projects_can_hydrate_after_refresh(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.setattr(projects_api, "_choose_directory", lambda: repo)
    client = TestClient(create_app())

    opened = client.post("/api/projects/choose-local").json()["data"]
    response = client.get("/api/projects")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"][0]["id"] == opened["id"]
    assert data["items"][0]["rootPath"] == str(repo)


def test_bootstrap_failure_returns_terminal_error(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.setattr(projects_api, "_choose_directory", lambda: repo)

    def fail_bootstrap(self, project_id: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(bootstrap_module.ProjectBootstrapService, "bootstrap", fail_bootstrap)

    response = TestClient(create_app()).post("/api/projects/choose-local")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROJECT_BOOTSTRAP_FAILED"


def test_folder_picker_cancel_returns_terminal_error(monkeypatch) -> None:
    monkeypatch.setattr(projects_api, "_choose_directory", lambda: None)

    response = TestClient(create_app()).post("/api/projects/choose-local")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_SELECTION_CANCELLED"


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    (repo / "app.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "ignored.py").write_text("def ignored():\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo
