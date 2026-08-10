from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.api.state import STATE
from se_mentor.main import create_app


def test_T089_recovery_required_blocks_execute_until_resolved() -> None:
    client = TestClient(create_app())
    task_id = STATE.new_id("task")
    STATE.tasks[task_id] = {"id": task_id, "status": "CREATED", "recoveryRequired": True}

    blocked = client.post(f"/api/tasks/{task_id}/execute", json={"command": "APPLY_PATCH"})
    recovery = client.get("/api/recovery")
    resolved = client.post(f"/api/recovery/{task_id}/resolve", json={"action": "rollback"})
    allowed = client.post(f"/api/tasks/{task_id}/execute", json={"command": "APPLY_PATCH"})

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "RECOVERY_REQUIRED"
    assert recovery.json()["data"]["items"][0]["taskId"] == task_id
    assert resolved.json()["data"]["status"] == "RESOLVED"
    assert allowed.status_code == 200
