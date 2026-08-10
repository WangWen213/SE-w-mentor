from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_T094_project_task_list_and_proposal_review_contract() -> None:
    client = TestClient(create_app())

    project = client.post("/api/projects", json={"rootPath": "C:/repo"}).json()["data"]
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
    assert tasks.json()["data"]["items"][0]["id"] == task["id"]
    assert current.status_code == 200
    assert current.json()["data"]["missingInformationQuestion"] == "Which module should change?"
    assert adjusted.status_code == 200
    assert adjusted.json()["data"]["version"] == 2
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"
    assert missing_adjustment.status_code == 400
    assert missing_adjustment.json()["error"]["code"] == "PROPOSAL_ADJUSTMENT_REQUIRED"
