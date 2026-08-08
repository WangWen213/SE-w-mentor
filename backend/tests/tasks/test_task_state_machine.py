from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.audit import AuditEvent
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.tasks.task_service import TaskCreationRequest, TaskService


def test_T024_created_cannot_jump_to_completed_and_blocked_cannot_execute(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "tasks.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    service = TaskService(session_factory)

    with session_scope(session_factory) as session:
        result = service.transition(
            ids["task_id"],
            TaskStatus.COMPLETED,
            actor_id="agent",
            idempotency_key="jump",
            session=session,
        )
        assert result.accepted is False
        assert result.reason == "ILLEGAL_TRANSITION"
        assert session.get(ChangeTask, ids["task_id"]).status == TaskStatus.CREATED
        assert session.query(AuditEvent).count() == 0

        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.BLOCKED
        task.failure_code = "MISSING_REQUIRED_CONFIG"
        session.flush()

        blocked = service.transition(
            ids["task_id"],
            TaskStatus.EXECUTING,
            actor_id="agent",
            idempotency_key="blocked-exec",
            session=session,
        )
        assert blocked.accepted is False
        assert blocked.reason == "BLOCKED_TASK_CANNOT_EXECUTE"
        assert session.get(ChangeTask, ids["task_id"]).status == TaskStatus.BLOCKED
        assert session.query(AuditEvent).count() == 0

    created = service.create_task(
        TaskCreationRequest(
            project_id=ids["project_id"],
            original_request="make a scoped change",
            requester_id="user",
            base_revision="a" * 40,
            token_budget=2048,
        ),
        actor_id="user",
        idempotency_key="create-1",
    )
    repeated = service.create_task(
        TaskCreationRequest(
            project_id=ids["project_id"],
            original_request="make a scoped change",
            requester_id="user",
            base_revision="a" * 40,
            token_budget=2048,
        ),
        actor_id="user",
        idempotency_key="create-1",
    )
    assert repeated.task_id == created.task_id
    assert created.status is TaskStatus.CREATED
