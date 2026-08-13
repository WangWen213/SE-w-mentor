from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.api import execution
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.main import create_app
from se_mentor.models.task import ChangeTask, TaskStatus


def test_cancel_response_returns_authoritative_task_snapshot(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "cancel-state-sync.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    execution.set_execution_authority_dependencies(
        session_factory=session_factory,
        runtime=FakeRuntime(),
        reset_orchestrator=True,
    )
    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.EXECUTING
        task_request = task.original_request

    client = TestClient(create_app())
    execution.set_execution_authority_dependencies(
        session_factory=session_factory,
        orchestrator=FakeCancelOrchestrator(),
    )
    response = client.post(f"/api/tasks/{ids['task_id']}/cancel")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "CANCEL_REQUESTED"
    assert payload["task"] == {
        "id": ids["task_id"],
        "projectId": ids["project_id"],
        "request": task_request,
        "status": "CANCEL_REQUESTED",
    }


class FakeRuntime:
    pass


class FakeCancelResult:
    task_id = "unused"
    status = "CANCEL_REQUESTED"
    event_id = 7

    def payload(self) -> dict[str, object]:
        return {"taskId": self.task_id, "status": self.status, "eventId": self.event_id}


class FakeCancelOrchestrator:
    def execute_task(self, task_id: str, *, command: str) -> FakeCancelResult:
        raise AssertionError("execute should not be called")

    def cancel_task(self, task_id: str) -> FakeCancelResult:
        result = FakeCancelResult()
        result.task_id = task_id
        return result
