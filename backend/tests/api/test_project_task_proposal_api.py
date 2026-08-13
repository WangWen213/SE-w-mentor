from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return path


def test_T086_project_task_proposal_routes_initially_404(tmp_path: Path) -> None:
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")

    project = client.post("/api/projects", json={"rootPath": str(repo)})
    duplicate_project = client.post("/api/projects", json={"rootPath": str(repo)})
    project_id = project.json()["data"]["id"]
    task = client.post("/api/tasks", json={"projectId": project_id, "request": "change app"})
    task_id = task.json()["data"]["id"]
    proposal = client.post(f"/api/tasks/{task_id}/proposals", json={"goal": "change app"})

    assert project.status_code == 201
    assert duplicate_project.status_code == 200
    assert duplicate_project.json()["data"]["id"] == project_id
    assert task.status_code == 201
    assert proposal.status_code == 201
    assert project.json()["error"] is None
    assert project.json()["data"]["rootPath"] == str(repo.resolve())
    assert task.json()["error"] is None
    assert proposal.json()["error"] is None
