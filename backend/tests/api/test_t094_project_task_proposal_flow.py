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


def test_T094_project_task_list_and_proposal_review_contract(tmp_path: Path) -> None:
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")

    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change app"},
    ).json()["data"]
    proposal_v1 = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={
            "goal": "change app",
            "missingInformationQuestion": "Which module should change?",
        },
    ).json()["data"]

    tasks = client.get(f"/api/projects/{project['id']}/tasks")
    current = client.get(f"/api/tasks/{task['id']}/proposals")
    adjusted = client.post(
        f"/api/tasks/{task['id']}/proposals/{proposal_v1['id']}/adjust",
        json={"instruction": "change user module only"},
    )
    confirmed = client.post(
        f"/api/tasks/{task['id']}/proposals/{adjusted.json()['data']['id']}/confirm",
    )
    missing_adjustment = client.post(
        f"/api/tasks/{task['id']}/proposals/{proposal_v1['id']}/adjust",
        json={"instruction": ""},
    )

    assert tasks.status_code == 200
    assert project["rootPath"] == str(repo.resolve())
    assert tasks.json()["data"]["items"][0]["id"] == task["id"]
    assert current.status_code == 200
    assert current.json()["data"]["missingInformationQuestion"] == "Which module should change?"
    assert adjusted.status_code == 200
    assert adjusted.json()["data"]["version"] == 2
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"
    assert missing_adjustment.status_code == 400
    assert missing_adjustment.json()["error"]["code"] == "PROPOSAL_ADJUSTMENT_REQUIRED"
