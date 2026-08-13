from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_T087_unconfirmed_proposal_cannot_run_governance() -> None:
    client = TestClient(create_app())
    project = client.post("/api/projects", json={"rootPath": "C:/repo"}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change public API"},
    ).json()["data"]
    proposal = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={"goal": "change public API"},
    ).json()["data"]

    response = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": ["public_api.py"], "prompt": "system sk-proj-abcdefghijklmnop"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "PROPOSAL_NOT_CONFIRMED"
    assert "sk-proj" not in str(body)
    assert "system" not in str(body)
