from __future__ import annotations

import json
from typing import Protocol

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.agent.runtime import AgentRuntime
from se_mentor.api.envelope import error, ok
from se_mentor.api.events import BUS
from se_mentor.api.state import STATE
from se_mentor.db.session import session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import WorkspaceLockMode
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService

router = APIRouter(prefix="/api/tasks", tags=["execution"])
_SESSION_FACTORY: sessionmaker[Session] | None = None
_RUNTIME: AgentRuntime | None = None


class ExecuteRequest(BaseModel):
    command: str


def _tool_calls(task: dict[str, object]) -> int:
    value = task.get("toolCalls", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


class ExecutionAuthority(Protocol):
    def execute(self, *, task_id: str, command: str) -> dict[str, object]: ...

    def cancel(self, *, task_id: str) -> dict[str, object]: ...


class BackendExecutionAuthority:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None,
        runtime: AgentRuntime | None,
    ) -> None:
        self._session_factory = session_factory
        self._runtime = runtime

    def execute(self, *, task_id: str, command: str) -> dict[str, object]:
        if self._session_factory is None:
            raise ValueError("execution authority unavailable")
        with session_scope(self._session_factory) as session:
            task = session.get(ChangeTask, task_id)
            if task is None:
                raise ValueError("task not found")
            if task.status == TaskStatus.BLOCKED:
                raise PermissionError("blocked tasks cannot execute tools")
            policy = _active_policy(session, task)
            if policy is None or not policy.executable:
                raise PermissionError("explicit approval required before execution")
            commands = _json_tuple(policy.commands_json)
            if command not in commands:
                raise PermissionError("command outside execution policy")
            grant = TemporaryGrantService(session).create(
                policy.id,
                write_paths=_json_tuple(policy.write_paths_json),
                commands=(command,),
            )
            lock_result = WorkspaceLockService(self._session_factory).acquire(
                project_id=task.project_id,
                task_id=task.id,
                mode=WorkspaceLockMode.WRITE,
                owner_instance="api-execution",
                reason="execute task",
                session=session,
            )
            if lock_result.status != LockAcquireStatus.ACQUIRED or lock_result.lock is None:
                raise BlockingIOError(lock_result.status)
            task.workspace_lock_id = lock_result.lock.id
            task.active_policy_id = policy.id
            task.status = TaskStatus.EXECUTING
            if self._runtime is not None:
                self._runtime.run_once(
                    task_id=task.id,
                    proposal_hash=grant.proposal_hash,
                    revision=grant.revision,
                    goal=command,
                )
            event = BUS.publish(
                task_id=task_id,
                event_type="EXECUTION_STARTED",
                payload={
                    "projectId": task.project_id,
                    "taskId": task_id,
                    "state": "EXECUTING",
                    "message": "execution started",
                },
            )
            return {
                "taskId": task_id,
                "command": command,
                "status": "EXECUTING",
                "eventId": event.event_id,
                "lockId": lock_result.lock.id,
                "policyId": policy.id,
            }

    def cancel(self, *, task_id: str) -> dict[str, object]:
        runtime = self._runtime or AgentRuntime()
        runtime.request_cancel(task_id=task_id, reason="user requested cancellation")
        event = BUS.publish(
            task_id=task_id,
            event_type="CANCEL_REQUESTED",
            payload={
                "taskId": task_id,
                "state": "CANCEL_REQUESTED",
                "message": "cancel requested",
            },
        )
        return {"taskId": task_id, "status": "CANCEL_REQUESTED", "eventId": event.event_id}


def set_execution_authority_dependencies(
    *,
    session_factory: sessionmaker[Session] | None = None,
    runtime: AgentRuntime | None = None,
) -> None:
    global _SESSION_FACTORY, _RUNTIME
    _SESSION_FACTORY = session_factory
    _RUNTIME = runtime


def get_execution_authority() -> ExecutionAuthority:
    return BackendExecutionAuthority(_SESSION_FACTORY, _RUNTIME)


@router.post("/{task_id}/execute")
def execute(task_id: str, payload: ExecuteRequest, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    if task.get("status") == "BLOCKED":
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("TASK_BLOCKED", "blocked tasks cannot execute tools")
    if task.get("recoveryRequired"):
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("RECOVERY_REQUIRED", "resolve recovery before executing tools")
    try:
        result = get_execution_authority().execute(task_id=task_id, command=payload.command)
    except PermissionError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("EXECUTION_REJECTED", str(exc))
    except BlockingIOError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("LOCK_CONFLICT", str(exc))
    except ValueError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("EXECUTION_UNAVAILABLE", str(exc))
    task["toolCalls"] = _tool_calls(task) + 1
    task["status"] = result.get("status", "EXECUTING")
    return ok(result)


@router.post("/{task_id}/cancel")
def cancel(task_id: str, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    try:
        return ok(get_execution_authority().cancel(task_id=task_id))
    except ValueError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CANCEL_REJECTED", str(exc))


@router.get("/{task_id}/policy")
def policy(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    return ok({"taskId": task_id, "writePaths": [], "commands": []})


def _active_policy(session: Session, task: ChangeTask) -> ExecutionPolicy | None:
    if task.active_policy_id is not None:
        policy = session.get(ExecutionPolicy, task.active_policy_id)
        if policy is not None and policy.status == ExecutionPolicyStatus.ACTIVE:
            return policy
    return session.scalar(
        select(ExecutionPolicy)
        .where(ExecutionPolicy.task_id == task.id)
        .where(ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE)
    )


def _json_tuple(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data)
