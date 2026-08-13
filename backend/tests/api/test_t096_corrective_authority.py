from __future__ import annotations

import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from se_mentor.api.approvals import BackendApprovalAuthority
from se_mentor.api.execution import set_execution_authority_dependencies
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.execution.orchestrator import ExecutionOrchestrator
from se_mentor.main import create_app
from se_mentor.models.task import ChangeTask, TaskStatus


def test_T096_corrective_approval_uses_authoritative_grant_and_policy(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeAuthority:
        def approve(
            self, *, approval_id: str, approved_scope: tuple[str, ...]
        ) -> dict[str, object]:
            calls.append(("approve", approval_id))
            return {
                "id": approval_id,
                "status": "APPROVED",
                "approvedScope": list(approved_scope),
                "temporaryGrant": {
                    "id": "grant-from-service",
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

    monkeypatch.setattr(
        "se_mentor.api.approvals.get_approval_authority", lambda: FakeAuthority(), raising=False
    )

    response = TestClient(create_app()).post(
        "/api/approvals/approval-1/approve",
        json={"approvedScope": ["auth/middleware.py"]},
    )

    assert response.status_code == 200, response.text
    assert calls == [("approve", "approval-1")]
    data = response.json()["data"]
    assert data["temporaryGrant"]["id"] == "grant-from-service"
    assert data["executionPolicy"]["id"] == "policy-1"


def test_T096_corrective_execute_uses_lock_and_runtime_authority(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    class FakeAuthority:
        def execute_task(self, task_id: str, *, command: str):
            calls.append(("execute", task_id))
            return SimpleNamespace(
                payload=lambda: {
                    "taskId": task_id,
                    "command": command,
                    "status": "EXECUTING",
                    "eventId": 1,
                    "lockId": "lock-from-service",
                },
                status="EXECUTING",
            )

    client = TestClient(create_app())
    set_execution_authority_dependencies(
        session_factory=get_session_factory(),
        orchestrator=FakeAuthority(),
    )
    task_id = _create_api_task(client, tmp_path)

    response = client.post(f"/api/tasks/{task_id}/execute", json={"command": "RUN_COMMAND"})

    assert response.status_code == 200, response.text
    assert calls == [("execute", task_id)]
    assert response.json()["data"]["lockId"] == "lock-from-service"


def test_T096_corrective_cancel_uses_runtime_cancel_without_terminal_state(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    class FakeAuthority:
        def cancel_task(self, task_id: str):
            calls.append(("cancel", task_id))
            return SimpleNamespace(
                payload=lambda: {"taskId": task_id, "status": "CANCEL_REQUESTED", "eventId": 2}
            )

    client = TestClient(create_app())
    set_execution_authority_dependencies(
        session_factory=get_session_factory(),
        orchestrator=FakeAuthority(),
    )
    task_id = _create_api_task(client, tmp_path)
    response = client.post(f"/api/tasks/{task_id}/cancel")

    assert response.status_code == 200
    assert calls == [("cancel", task_id)]


def test_T096_corrective_hard_block_cannot_be_approved_or_executed(monkeypatch, tmp_path) -> None:
    class FakeAuthority:
        def approve(
            self, *, approval_id: str, approved_scope: tuple[str, ...]
        ) -> dict[str, object]:
            raise ValueError("deny hard decision cannot be approved")

    monkeypatch.setattr(
        "se_mentor.api.approvals.get_approval_authority", lambda: FakeAuthority(), raising=False
    )
    client = TestClient(create_app())
    task_id = _create_api_task(client, tmp_path)
    with session_scope(get_session_factory()) as session:
        task = session.get(ChangeTask, task_id)
        assert task is not None
        task.status = TaskStatus.BLOCKED

    approved = client.post(
        "/api/approvals/blocked-approval/approve", json={"approvedScope": ["x.py"]}
    )
    executed = client.post(f"/api/tasks/{task_id}/execute", json={"command": "RUN_COMMAND"})

    assert approved.status_code == 409
    assert executed.status_code == 409


def test_T096_corrective_backend_approval_authority_calls_grant_service(monkeypatch) -> None:
    calls: list[str] = []
    request = SimpleNamespace(
        id="approval-1",
        task_id="task-1",
        governance_decision_id="decision-1",
    )
    policy = SimpleNamespace(
        id="policy-1",
        executable=True,
        commands_json='["RUN_COMMAND"]',
        status="ACTIVE",
    )

    class FakeSession:
        def get(self, _model, _id):
            return request

        def scalar(self, _statement):
            return policy

    @contextmanager
    def fake_session_scope(_factory):
        yield FakeSession()

    class FakeDecisionService:
        def __init__(self, _session) -> None:
            pass

        def record(self, **_kwargs):
            calls.append("ApprovalDecisionService.record")
            return SimpleNamespace(outcome="APPROVED")

    class FakeGrantService:
        def __init__(self, _session) -> None:
            pass

        def create(self, policy_id, *, write_paths, commands):
            calls.append("TemporaryGrantService.create")
            return SimpleNamespace(
                task_id="task-1",
                policy_id=policy_id,
                proposal_hash="a" * 64,
                revision="rev-1",
                write_paths=tuple(write_paths),
                commands=tuple(commands),
            )

    monkeypatch.setattr("se_mentor.api.approvals.session_scope", fake_session_scope)
    monkeypatch.setattr("se_mentor.api.approvals.ApprovalDecisionService", FakeDecisionService)
    monkeypatch.setattr("se_mentor.api.approvals.TemporaryGrantService", FakeGrantService)

    result = BackendApprovalAuthority(object()).approve(
        approval_id="approval-1",
        approved_scope=("auth/middleware.py",),
    )

    assert calls == ["ApprovalDecisionService.record", "TemporaryGrantService.create"]
    assert result["executionPolicy"]["id"] == "policy-1"


def test_T096_corrective_orchestrator_cancel_calls_agent_runtime_request_cancel() -> None:
    calls: list[tuple[str, str]] = []

    class FakeRuntime:
        def request_cancel(self, *, task_id: str, reason: str) -> None:
            calls.append((task_id, reason))

    result = ExecutionOrchestrator(object(), runtime=FakeRuntime()).cancel_task("task-1")

    assert calls == [("task-1", "user requested cancellation")]
    assert result.status == "CANCEL_REQUESTED"


def _create_api_task(client: TestClient, tmp_path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change auth"},
    ).json()["data"]
    return str(task["id"])
