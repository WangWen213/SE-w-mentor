from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.api.state import STATE
from se_mentor.main import create_app


def test_T092_file_change_reverse_trace_and_full_replay_are_complete() -> None:
    client = TestClient(create_app())
    task_id = STATE.new_id("task")
    change_id = STATE.new_id("change")
    STATE.tasks[task_id] = {"id": task_id, "status": "COMPLETED"}
    STATE.replay[task_id] = [
        {"eventId": 1, "kind": "action", "actionId": "action-1"},
        {"eventId": 2, "kind": "tool", "toolExecutionId": "tool-1"},
    ]
    STATE.file_changes[change_id] = {
        "taskId": task_id,
        "path": "app.py",
        "agentActionId": "action-1",
        "governanceDecisionId": "decision-1",
        "executionPolicyId": "policy-1",
        "toolExecutionId": "tool-1",
        "approvalId": "approval-1",
    }

    trace = client.get(f"/api/diffs/{change_id}/trace")
    replay = client.get(f"/api/tasks/{task_id}/replay")

    assert trace.status_code == 200
    assert trace.json()["data"]["agentActionId"] == "action-1"
    assert trace.json()["data"]["executionPolicyId"] == "policy-1"
    assert [item["eventId"] for item in replay.json()["data"]["events"]] == [1, 2]
