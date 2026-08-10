from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    project_id: str = Field(alias="projectId")
    request: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, response: Response) -> dict[str, object]:
    if payload.project_id not in STATE.projects:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROJECT_NOT_FOUND", "project not found")
    if not payload.request.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("TASK_REQUEST_REQUIRED", "task request is required")
    task_id = STATE.new_id("task")
    STATE.tasks[task_id] = {
        "id": task_id,
        "projectId": payload.project_id,
        "request": payload.request,
        "status": "CREATED",
    }
    return ok({"id": task_id, "projectId": payload.project_id, "status": "CREATED"})


@router.get("/{task_id}")
def get_task(task_id: str, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    return ok(dict(task))
