from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from se_mentor.api.approvals import BackendApprovalAuthority
from se_mentor.api.execution import BackendExecutionAuthority
from se_mentor.api.state import STATE
from se_mentor.main import create_app


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

    assert response.status_code == 200
    assert calls == [("approve", "approval-1")]
    data = response.json()["data"]
    assert data["temporaryGrant"]["id"] == "grant-from-service"
    assert data["executionPolicy"]["id"] == "policy-1"


def test_T096_corrective_execute_uses_lock_and_runtime_authority(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeAuthority:
        def execute(self, *, task_id: str, command: str) -> dict[str, object]:
            calls.append(("execute", task_id))
            return {
                "taskId": task_id,
                "command": command,
                "status": "EXECUTING",
                "eventId": 1,
                "lockId": "lock-from-service",
            }

    monkeypatch.setattr(
        "se_mentor.api.execution.get_execution_authority", lambda: FakeAuthority(), raising=False
    )
    STATE.tasks["task-1"] = {"id": "task-1", "projectId": "project-1", "status": "CREATED"}

    response = TestClient(create_app()).post(
        "/api/tasks/task-1/execute", json={"command": "RUN_COMMAND"}
    )

    assert response.status_code == 200
    assert calls == [("execute", "task-1")]
    assert response.json()["data"]["lockId"] == "lock-from-service"


def test_T096_corrective_cancel_uses_runtime_cancel_without_terminal_state(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeAuthority:
        def cancel(self, *, task_id: str) -> dict[str, object]:
            calls.append(("cancel", task_id))
            return {"taskId": task_id, "status": "CANCEL_REQUESTED", "eventId": 2}

    monkeypatch.setattr(
        "se_mentor.api.execution.get_execution_authority", lambda: FakeAuthority(), raising=False
    )
    STATE.tasks["task-2"] = {"id": "task-2", "projectId": "project-1", "status": "EXECUTING"}

    response = TestClient(create_app()).post("/api/tasks/task-2/cancel")

    assert response.status_code == 200
    assert calls == [("cancel", "task-2")]
    assert STATE.tasks["task-2"]["status"] == "EXECUTING"


def test_T096_corrective_hard_block_cannot_be_approved_or_executed(monkeypatch) -> None:
    class FakeAuthority:
        def approve(
            self, *, approval_id: str, approved_scope: tuple[str, ...]
        ) -> dict[str, object]:
            raise ValueError("deny hard decision cannot be approved")

    monkeypatch.setattr(
        "se_mentor.api.approvals.get_approval_authority", lambda: FakeAuthority(), raising=False
    )
    STATE.tasks["blocked-task"] = {
        "id": "blocked-task",
        "projectId": "project-1",
        "status": "BLOCKED",
    }
    client = TestClient(create_app())

    approved = client.post(
        "/api/approvals/blocked-approval/approve", json={"approvedScope": ["x.py"]}
    )
    executed = client.post("/api/tasks/blocked-task/execute", json={"command": "RUN_COMMAND"})

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


def test_T096_corrective_backend_execution_authority_calls_lock_and_runtime(monkeypatch) -> None:
    calls: list[str] = []
    task = SimpleNamespace(
        id="task-1",
        project_id="project-1",
        status="CREATED",
        active_policy_id=None,
        workspace_lock_id=None,
    )
    policy = SimpleNamespace(
        id="policy-1",
        executable=True,
        commands_json='["RUN_COMMAND"]',
        write_paths_json='["auth/middleware.py"]',
        status="ACTIVE",
        proposal_hash="a" * 64,
        revision="rev-1",
    )

    class FakeSession:
        def get(self, model, _id):
            name = getattr(model, "__name__", "")
            return task if name == "ChangeTask" else policy

        def scalar(self, _statement):
            return policy

    @contextmanager
    def fake_session_scope(_factory):
        yield FakeSession()

    class FakeGrantService:
        def __init__(self, _session) -> None:
            pass

        def create(self, policy_id, *, write_paths, commands):
            calls.append("TemporaryGrantService.create")
            return SimpleNamespace(
                policy_id=policy_id,
                proposal_hash="a" * 64,
                revision="rev-1",
                write_paths=tuple(write_paths),
                commands=tuple(commands),
            )

    class FakeLockService:
        def __init__(self, _factory) -> None:
            pass

        def acquire(self, **_kwargs):
            calls.append("WorkspaceLockService.acquire")
            return SimpleNamespace(
                status="ACQUIRED",
                lock=SimpleNamespace(id="lock-1"),
            )

    class FakeRuntime:
        def run_once(self, **_kwargs):
            calls.append("AgentRuntime.run_once")

    monkeypatch.setattr("se_mentor.api.execution.session_scope", fake_session_scope)
    monkeypatch.setattr("se_mentor.api.execution.TemporaryGrantService", FakeGrantService)
    monkeypatch.setattr("se_mentor.api.execution.WorkspaceLockService", FakeLockService)

    result = BackendExecutionAuthority(object(), FakeRuntime()).execute(
        task_id="task-1",
        command="RUN_COMMAND",
    )

    assert calls == [
        "TemporaryGrantService.create",
        "WorkspaceLockService.acquire",
        "AgentRuntime.run_once",
    ]
    assert result["lockId"] == "lock-1"


def test_T096_corrective_backend_cancel_calls_agent_runtime_request_cancel() -> None:
    calls: list[tuple[str, str]] = []

    class FakeRuntime:
        def request_cancel(self, *, task_id: str, reason: str) -> None:
            calls.append((task_id, reason))

    result = BackendExecutionAuthority(None, FakeRuntime()).cancel(task_id="task-1")

    assert calls == [("task-1", "user requested cancellation")]
    assert result["status"] == "CANCEL_REQUESTED"
