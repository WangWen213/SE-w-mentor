from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.agent.runtime import AgentRuntime, ExecutionPipelineUnavailable
from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_task_access
from se_mentor.api.online_readiness import (
    OnlineSafeReadiness,
    require_online_safe_project_readiness,
)
from se_mentor.api.runtime import (
    get_runtime_settings,
)
from se_mentor.db.session import session_scope
from se_mentor.execution.orchestrator import (
    ExecutionOrchestrator,
    ExecutionOrchestratorProtocol,
    ExecutionRejected,
)
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.runtime.profiles import RuntimeProfile

router = APIRouter(prefix="/api/tasks", tags=["execution"])
_SESSION_FACTORY: sessionmaker[Session] | None = None
_RUNTIME: AgentRuntime | None = None
_ORCHESTRATOR: ExecutionOrchestratorProtocol | None = None


class ExecuteRequest(BaseModel):
    command: str


def set_execution_authority_dependencies(
    *,
    session_factory: sessionmaker[Session] | None = None,
    runtime: AgentRuntime | None = None,
    orchestrator: ExecutionOrchestratorProtocol | None = None,
    reset_orchestrator: bool = False,
) -> None:
    global _SESSION_FACTORY, _RUNTIME, _ORCHESTRATOR
    if session_factory is not None:
        _SESSION_FACTORY = session_factory
    if runtime is not None:
        _RUNTIME = runtime
    if reset_orchestrator:
        _ORCHESTRATOR = None
    if orchestrator is not None:
        _ORCHESTRATOR = orchestrator


def get_execution_orchestrator() -> ExecutionOrchestratorProtocol:
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    if _SESSION_FACTORY is None:
        raise ExecutionRejected("EXECUTION_UNAVAILABLE", "execution authority unavailable")
    return ExecutionOrchestrator(_SESSION_FACTORY, runtime=_RUNTIME)


@router.post("/{task_id}/execute")
def execute(
    task_id: str,
    payload: ExecuteRequest,
    request: Request,
    response: Response,
) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if _SESSION_FACTORY is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("EXECUTION_UNAVAILABLE", "execution authority unavailable")
        with session_scope(_SESSION_FACTORY) as session:
            task = require_task_access(session, task_id, request, response)
            if task is None:
                response.status_code = status.HTTP_404_NOT_FOUND
                return error("TASK_NOT_FOUND", "task not found")
            readiness = require_online_safe_project_readiness(
                session,
                task.project_id,
                request,
                response,
            )
            if isinstance(readiness, dict):
                return readiness
        orchestrator = ExecutionOrchestrator(
            _SESSION_FACTORY,
            runtime=_RUNTIME,
            provider_override=readiness.provider
            if isinstance(readiness, OnlineSafeReadiness)
            else None,
        )
    else:
        orchestrator = get_execution_orchestrator()
    if _SESSION_FACTORY is None:
        response.status_code = status.HTTP_409_CONFLICT
        return error("EXECUTION_UNAVAILABLE", "execution authority unavailable")
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        if task.status == TaskStatus.BLOCKED:
            response.status_code = status.HTTP_409_CONFLICT
            return error("TASK_BLOCKED", "blocked tasks cannot execute tools")
    try:
        result = orchestrator.execute_task(task_id, command=payload.command)
    except ExecutionRejected as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error(exc.code, _safe_error(exc))
    except PermissionError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error("EXECUTION_REJECTED", str(exc))
    except ExecutionPipelineUnavailable as exc:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error(exc.code, _safe_error(exc))
    except Exception as exc:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error(getattr(exc, "code", "EXECUTION_FAILED"), _safe_error(exc))
    if result.status == "FAILED":
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error(
            str(result.code or "EXECUTION_FAILED"), str(result.error or "execution failed")
        )
    return ok(result.payload())


@router.post("/{task_id}/cancel")
def cancel(task_id: str, request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if _SESSION_FACTORY is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("EXECUTION_UNAVAILABLE", "execution authority unavailable")
        with session_scope(_SESSION_FACTORY) as session:
            if require_task_access(session, task_id, request, response) is None:
                response.status_code = status.HTTP_404_NOT_FOUND
                return error("TASK_NOT_FOUND", "task not found")
    if _SESSION_FACTORY is not None:
        with session_scope(_SESSION_FACTORY) as session:
            task = require_task_access(session, task_id, request, response)
            if task is None:
                response.status_code = status.HTTP_404_NOT_FOUND
                return error("TASK_NOT_FOUND", "task not found")
    try:
        payload = get_execution_orchestrator().cancel_task(task_id).payload()
    except ExecutionRejected as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error(exc.code, _safe_error(exc))
    except ValueError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CANCEL_REJECTED", str(exc))
    if _SESSION_FACTORY is not None:
        with session_scope(_SESSION_FACTORY) as session:
            task = session.get(ChangeTask, task_id)
            if task is not None:
                payload["task"] = _task_payload(task, fallback_status=str(payload["status"]))
    return ok(payload)


@router.get("/{task_id}/policy")
def policy(task_id: str, request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if _SESSION_FACTORY is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("EXECUTION_UNAVAILABLE", "execution authority unavailable")
        with session_scope(_SESSION_FACTORY) as session:
            if require_task_access(session, task_id, request, response) is None:
                response.status_code = status.HTTP_404_NOT_FOUND
                return error("TASK_NOT_FOUND", "task not found")
    if _SESSION_FACTORY is None:
        response.status_code = status.HTTP_409_CONFLICT
        return error("EXECUTION_UNAVAILABLE", "execution authority unavailable")
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        policy_row = _active_policy(session, task)
        if policy_row is None:
            return ok({"taskId": task_id, "writePaths": [], "commands": []})
        return ok(
            {
                "taskId": task_id,
                "writePaths": list(_json_tuple(policy_row.write_paths_json)),
                "commands": list(_json_tuple(policy_row.commands_json)),
            }
        )


def _safe_error(exc: Exception) -> str:
    return " ".join((str(exc) or type(exc).__name__).split())[:360]


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


def _task_payload(task: ChangeTask, *, fallback_status: str | None = None) -> dict[str, object]:
    status_value = fallback_status if fallback_status == "CANCEL_REQUESTED" else str(task.status)
    return {
        "id": task.id,
        "projectId": task.project_id,
        "request": task.original_request,
        "status": status_value,
    }
