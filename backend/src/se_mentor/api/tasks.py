from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.git.git_service import GitService
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.tasks.task_service import TaskCreationRequest, TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
_SESSION_FACTORY = get_session_factory()
_TASK_SERVICE = TaskService(_SESSION_FACTORY)
LOGGER = logging.getLogger("se_mentor.api.tasks")


class TaskCreate(BaseModel):
    project_id: str = Field(alias="projectId")
    request: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, response: Response) -> dict[str, object]:
    if not payload.request.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("TASK_REQUEST_REQUIRED", "task request is required")
    with session_scope(_SESSION_FACTORY) as session:
        project = session.get(Project, payload.project_id)
        if project is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        try:
            base_revision = GitService(project.root_path).base_revision()
        except Exception as exc:
            LOGGER.exception("TASK_CREATE git baseline failed project_id=%s", payload.project_id)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("TASK_CREATE_FAILED", str(exc))
    try:
        result = _TASK_SERVICE.create_task(
            TaskCreationRequest(
                project_id=payload.project_id,
                original_request=payload.request.strip(),
                requester_id="webui-user",
                base_revision=base_revision,
                token_budget=8192,
            ),
            actor_id="webui-user",
            idempotency_key=f"task-create:{uuid4()}",
        )
    except ValueError as exc:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("TASK_CREATE_FAILED", str(exc))
    except Exception as exc:
        LOGGER.exception("TASK_CREATE failed project_id=%s", payload.project_id)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error("TASK_CREATE_FAILED", str(exc))
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, result.task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        session.add(
            WorkbenchMessage(
                task_id=task.id,
                sequence=1,
                role="USER",
                kind="TEXT",
                status="DONE",
                text=task.original_request,
            )
        )
        payload_out = _task_payload(task)
    return ok(payload_out)


@router.get("/{task_id}")
def get_task(task_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        payload_out = _task_payload(task)
    return ok(payload_out)


def _task_payload(task: ChangeTask) -> dict[str, object]:
    return {
        "id": task.id,
        "projectId": task.project_id,
        "request": task.original_request,
        "status": task.status,
    }
