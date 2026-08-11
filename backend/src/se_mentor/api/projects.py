from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.projects.project_repository import find_project_by_root
from se_mentor.projects.project_service import ProjectRegistrationError, register_project

router = APIRouter(prefix="/api/projects", tags=["projects"])
_ENGINE = create_sqlite_engine(f"sqlite:///{Path(gettempdir()) / 'se_mentor_api.sqlite3'}")
Base.metadata.create_all(_ENGINE)
_SESSION_FACTORY = create_session_factory(_ENGINE)


class ProjectCreate(BaseModel):
    root_path: str = Field(alias="rootPath")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, response: Response) -> dict[str, object]:
    if not payload.root_path.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROJECT_PATH_REQUIRED", "project rootPath is required")
    try:
        with session_scope(_SESSION_FACTORY) as session:
            registered = register_project(
                session,
                payload.root_path,
                authorized_root=Path(payload.root_path).expanduser(),
            )
            project = registered.project
            project_id = project.id
            project_payload = {
                "id": project_id,
                "authorized": True,
                "rootPath": project.root_path,
                "revision": registered.current_revision,
            }
    except ProjectRegistrationError as exc:
        if "duplicate" in str(exc):
            with session_scope(_SESSION_FACTORY) as session:
                existing = find_project_by_root(
                    session, Path(payload.root_path).resolve(strict=True)
                )
                if existing is not None:
                    project_payload = {
                        "id": existing.id,
                        "authorized": True,
                        "rootPath": existing.root_path,
                    }
                    STATE.projects[existing.id] = dict(project_payload)
                    response.status_code = status.HTTP_200_OK
                    return ok(project_payload)
        response.status_code = (
            status.HTTP_409_CONFLICT if "duplicate" in str(exc) else status.HTTP_400_BAD_REQUEST
        )
        return error("PROJECT_REGISTRATION_FAILED", str(exc))

    STATE.projects[project_id] = dict(project_payload)
    return ok(project_payload)


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
