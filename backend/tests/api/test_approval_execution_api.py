from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.api.state import STATE
from se_mentor.main import create_app


def test_T088_blocked_task_execute_returns_conflict_and_no_tool_call() -> None:
    client = TestClient(create_app())
    task_id = STATE.new_id("task")
    STATE.tasks[task_id] = {
        "id": task_id,
        "projectId": "project-1",
        "request": "delete everything",
        "status": "BLOCKED",
    }

    response = client.post(f"/api/tasks/{task_id}/execute", json={"command": "APPLY_PATCH"})

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "TASK_BLOCKED"
    assert STATE.tasks[task_id].get("toolCalls", 0) == 0
