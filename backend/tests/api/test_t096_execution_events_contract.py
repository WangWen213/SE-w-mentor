from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.api.execution import set_execution_authority_dependencies
from se_mentor.api.runtime import get_session_factory
from se_mentor.main import create_app


def test_T096_approval_execution_cancel_and_events_contract(monkeypatch, tmp_path) -> None:
    class ApprovalAuthority:
        def approve(
            self, *, approval_id: str, approved_scope: tuple[str, ...]
        ) -> dict[str, object]:
            return {
                "id": approval_id,
                "status": "APPROVED",
                "approvedScope": list(approved_scope),
                "temporaryGrant": {
                    "id": "grant-policy-1",
                    "approvalId": approval_id,
                    "scope": list(approved_scope),
                    "status": "ACTIVE",
                    "taskId": "task-1",
                    "policyId": "policy-1",
                    "revision": "rev-1",
                },
                "executionPolicy": {
                    "id": "policy-1",
                    "approvalId": approval_id,
                    "writeAllowed": True,
                    "commands": ["RUN_COMMAND"],
                    "writePaths": list(approved_scope),
                    "status": "ACTIVE",
                },
            }

        def reject(self, *, approval_id: str) -> dict[str, object]:
            return {"id": approval_id, "status": "REJECTED"}

    class ExecutionAuthority:
        def execute_task(self, task_id: str, *, command: str):
            from se_mentor.api.events import BUS

            event = BUS.publish(
                task_id=task_id,
                event_type="EXECUTION_STARTED",
                payload={"taskId": task_id, "state": "EXECUTING", "message": "execution started"},
            )
            return SimpleResult(
                {
                    "taskId": task_id,
                    "command": command,
                    "status": "EXECUTING",
                    "eventId": event.event_id,
                }
            )

        def cancel_task(self, task_id: str):
            from se_mentor.api.events import BUS

            event = BUS.publish(
                task_id=task_id,
                event_type="CANCEL_REQUESTED",
                payload={
                    "taskId": task_id,
                    "state": "CANCEL_REQUESTED",
                    "message": "cancel requested",
                },
            )
            return SimpleResult(
                {"taskId": task_id, "status": "CANCEL_REQUESTED", "eventId": event.event_id}
            )

    monkeypatch.setattr(
        "se_mentor.api.approvals.get_approval_authority", lambda: ApprovalAuthority()
    )
    client = TestClient(create_app())
    set_execution_authority_dependencies(
        session_factory=get_session_factory(),
        orchestrator=ExecutionAuthority(),
    )
    repo = tmp_path / "repo"
    _git_repo(repo)
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
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


class SimpleResult:
    def __init__(self, payload: dict[str, object]) -> None:
        self.status = str(payload.get("status"))
        self._payload = payload

    def payload(self) -> dict[str, object]:
        return self._payload


def _git_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
