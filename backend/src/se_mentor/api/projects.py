from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    root_path: str = Field(alias="rootPath")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, response: Response) -> dict[str, object]:
    if not payload.root_path.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROJECT_PATH_REQUIRED", "project rootPath is required")
    project_id = STATE.new_id("project")
    STATE.projects[project_id] = {"id": project_id, "authorized": True}
    return ok({"id": project_id, "authorized": True})


@router.get("/{project_id}/config")
def project_config(project_id: str, response: Response) -> dict[str, object]:
    if project_id not in STATE.projects:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "secrets": "[redacted]"})


@router.get("/{project_id}/locks")
def lock_status(project_id: str, response: Response) -> dict[str, object]:
    if project_id not in STATE.projects:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "status": "UNLOCKED"})


@router.get("/{project_id}/tasks")
def list_project_tasks(project_id: str, response: Response) -> dict[str, object]:
    if project_id not in STATE.projects:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROJECT_NOT_FOUND", "project not found")
    tasks = [dict(task) for task in STATE.tasks.values() if task.get("projectId") == project_id]
    return ok({"projectId": project_id, "items": tasks})
