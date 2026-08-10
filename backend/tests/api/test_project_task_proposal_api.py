from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_T086_project_task_proposal_routes_initially_404() -> None:
    client = TestClient(create_app())

    project = client.post("/api/projects", json={"rootPath": "C:/repo"})
    project_id = project.json()["data"]["id"]
    task = client.post("/api/tasks", json={"projectId": project_id, "request": "change app"})
    task_id = task.json()["data"]["id"]
    proposal = client.post(f"/api/tasks/{task_id}/proposals", json={"goal": "change app"})

    assert project.status_code == 201
    assert task.status_code == 201
    assert proposal.status_code == 201
    assert project.json()["error"] is None
    assert task.json()["error"] is None
    assert proposal.json()["error"] is None
