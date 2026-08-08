from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from se_mentor.contracts.enums import EventType
from se_mentor.db.session import session_scope
from se_mentor.models.audit import AuditActorType, AuditEvent
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.tasks.state_machine import can_transition


@dataclass(frozen=True)
class TaskCreationRequest:
    project_id: str
    original_request: str
    requester_id: str | None
    base_revision: str | None
    token_budget: int


@dataclass(frozen=True)
class TaskCommandResult:
    accepted: bool
    reason: str
    task_id: str
    status: TaskStatus


class TaskService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._idempotency: dict[str, str] = {}

    def create_task(
        self,
        request: TaskCreationRequest,
        *,
        actor_id: str,
        idempotency_key: str,
    ) -> TaskCommandResult:
        existing = self._idempotency.get(idempotency_key)
        with session_scope(self._session_factory) as session:
            if existing is not None:
                task = session.get(ChangeTask, existing)
                if task is None:
                    raise ValueError("idempotent task disappeared")
                return TaskCommandResult(
                    True, "IDEMPOTENT_REPLAY", task.id, TaskStatus(task.status)
                )
            task = ChangeTask(
                project_id=request.project_id,
                requester_id=request.requester_id,
                original_request=request.original_request,
                base_revision=request.base_revision,
                base_workspace_hash=f"token_budget:{request.token_budget}",
                status=TaskStatus.CREATED,
            )
            session.add(task)
            session.flush()
            self._idempotency[idempotency_key] = task.id
            session.add(
                _audit(task.id, actor_id, "task created", {"token_budget": request.token_budget})
            )
            session.flush()
            return TaskCommandResult(True, "CREATED", task.id, TaskStatus(task.status))

    def transition(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        actor_id: str,
        idempotency_key: str,
        session: Session,
    ) -> TaskCommandResult:
        replay = self._idempotency.get(idempotency_key)
        task = session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        current = TaskStatus(task.status)
        if replay == f"{task_id}:{target}":
            return TaskCommandResult(True, "IDEMPOTENT_REPLAY", task_id, current)
        if current == TaskStatus.BLOCKED and target == TaskStatus.EXECUTING:
            return TaskCommandResult(False, "BLOCKED_TASK_CANNOT_EXECUTE", task_id, current)
        if not can_transition(current, target):
            return TaskCommandResult(False, "ILLEGAL_TRANSITION", task_id, current)
        task.status = target
        task.version += 1
        if target in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.BLOCKED,
        }:
            task.finished_at = datetime.now(UTC)
        session.add(
            _audit(task.id, actor_id, f"{current}->{target}", {"from": current, "to": target})
        )
        session.flush()
        self._idempotency[idempotency_key] = f"{task_id}:{target}"
        return TaskCommandResult(True, "TRANSITIONED", task_id, target)


def _audit(task_id: str, actor_id: str, summary: str, evidence: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        task_id=task_id,
        correlation_id=f"task:{task_id}:{summary}",
        actor_type=AuditActorType.USER,
        actor_id=actor_id,
        event_type=EventType.TASK_CREATED,
        payload_summary=summary,
        evidence_json=json.dumps(evidence),
    )
