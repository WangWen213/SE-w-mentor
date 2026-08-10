from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_T096_approval_execution_cancel_and_events_contract() -> None:
    client = TestClient(create_app())
    project = client.post("/api/projects", json={"rootPath": "C:/repo"}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change auth"},
    ).json()["data"]

    approved = client.post(
        "/api/approvals/approval-1/approve",
        json={"approvedScope": ["auth/middleware.py"]},
    )
    rejected = client.post("/api/approvals/approval-2/reject")
    executed = client.post(f"/api/tasks/{task['id']}/execute", json={"command": "RUN_COMMAND"})
    first_events = client.get(f"/api/tasks/{task['id']}/events")
    cancelled = client.post(f"/api/tasks/{task['id']}/cancel")
    replay = client.get(
        f"/api/tasks/{task['id']}/events",
        headers={"Last-Event-ID": str(executed.json()["data"]["eventId"])},
    )

    assert approved.status_code == 200
    assert approved.json()["data"]["temporaryGrant"]["status"] == "ACTIVE"
    assert approved.json()["data"]["executionPolicy"]["writeAllowed"] is True
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert executed.json()["data"]["status"] == "EXECUTING"
    assert "event: EXECUTION_STARTED" in first_events.text
    assert cancelled.json()["data"]["status"] == "CANCEL_REQUESTED"
    assert "event: CANCEL_REQUESTED" in replay.text
    assert "EXECUTION_STARTED" not in replay.text
