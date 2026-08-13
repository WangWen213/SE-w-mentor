from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.git.git_service import GitService
from se_mentor.models.knowledge import EngineeringKnowledge
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask
from se_mentor.projects.bootstrap import ProjectBootstrapService
from se_mentor.projects.project_repository import find_project_by_root
from se_mentor.projects.project_service import ProjectRegistrationError, register_project

router = APIRouter(prefix="/api/projects", tags=["projects"])
_SESSION_FACTORY = get_session_factory()
LOGGER = logging.getLogger("se_mentor.api.projects")
_BOOTSTRAP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="project-bootstrap")
_BOOTSTRAP_LOCK = Lock()
_BOOTSTRAP_STATES: dict[str, dict[str, object]] = {}
_BOOTSTRAP_READY_CACHE_TTL_SECONDS = 3.0
_BOOTSTRAP_READY_CACHE: dict[str, tuple[float, dict[str, object]]] = {}


class ProjectCreate(BaseModel):
    root_path: str = Field(alias="rootPath")


@router.get("")
def list_projects() -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        projects = session.scalars(select(Project).order_by(Project.updated_at.desc())).all()
        items = [
            _project_payload(project, bootstrap=_bootstrap_state(session, project.id))
            for project in projects
        ]
    LOGGER.info(
        "project.list total_ms=%s projects=%s",
        int((perf_counter() - started) * 1000),
        len(items),
    )
    return ok({"items": items})


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, response: Response) -> dict[str, object]:
    if not payload.root_path.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROJECT_PATH_REQUIRED", "project rootPath is required")
    return _register_project(payload.root_path, response)


@router.post("/choose-local", status_code=status.HTTP_201_CREATED)
def choose_local_project(response: Response) -> dict[str, object]:
    LOGGER.info("PROJECT_CHOOSE_LOCAL START")
    selected = _choose_directory()
    if selected is None:
        LOGGER.info("PROJECT_CHOOSE_LOCAL CANCEL")
        response.status_code = status.HTTP_409_CONFLICT
        return error("PROJECT_SELECTION_CANCELLED", "project selection was cancelled")
    LOGGER.info("PROJECT_CHOOSE_LOCAL SELECTED path=%s", selected)
    return _register_project(str(selected), response)


def _register_project(root_path: str, response: Response) -> dict[str, object]:
    LOGGER.info("PROJECT_REGISTER START root=%s", root_path)
    try:
        with session_scope(_SESSION_FACTORY) as session:
            registered = register_project(
                session,
                root_path,
                authorized_root=Path(root_path).expanduser(),
            )
            project = registered.project
            project_id = project.id
            LOGGER.info("PROJECT_REGISTER DONE project_id=%s", project_id)
            project_payload = _project_payload(project, bootstrap={"status": "REGISTERED"})
            project_payload["revision"] = registered.current_revision
            LOGGER.info("PROJECT_REGISTER RESPONSE project_id=%s", project_id)
    except ProjectRegistrationError as exc:
        if "duplicate" in str(exc):
            with session_scope(_SESSION_FACTORY) as session:
                existing = find_project_by_root(
                    session, Path(root_path).resolve(strict=True)
                )
                if existing is not None:
                    existing.updated_at = datetime.now(UTC)
                    session.flush()
                    existing_id = existing.id
                    LOGGER.info(
                        "PROJECT_REOPEN START project_id=%s root=%s",
                        existing_id,
                        root_path,
                    )
                    project_payload = _project_payload(
                        existing,
                        bootstrap=_schedule_bootstrap(existing_id),
                    )
                    project_payload["revision"] = _quick_revision(existing.root_path)
                    LOGGER.info("PROJECT_REOPEN RESPONSE project_id=%s", existing_id)
                    response.status_code = status.HTTP_200_OK
                    return ok(project_payload)
        response.status_code = (
            status.HTTP_409_CONFLICT if "duplicate" in str(exc) else status.HTTP_400_BAD_REQUEST
        )
        LOGGER.warning("PROJECT_REGISTER FAIL root=%s error=%s", root_path, exc)
        return error("PROJECT_REGISTRATION_FAILED", str(exc))
    except Exception as exc:
        LOGGER.exception("PROJECT_BOOTSTRAP FAIL root=%s", root_path)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error("PROJECT_BOOTSTRAP_FAILED", str(exc))

    project_payload["bootstrap"] = _schedule_bootstrap(str(project_payload["id"]))
    return ok(project_payload)


def _project_payload(project: Project, *, bootstrap: dict[str, object]) -> dict[str, object]:
    return {
        "id": project.id,
        "authorized": True,
        "rootPath": project.root_path,
        "bootstrap": bootstrap,
    }


@router.get("/{project_id}/bootstrap")
def bootstrap_status(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(Project, project_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        return ok(_bootstrap_state(session, project_id))


def _schedule_bootstrap(project_id: str) -> dict[str, object]:
    canonical = get_project_bootstrap_state(project_id)
    if canonical.get("status") == "READY":
        return canonical
    with _BOOTSTRAP_LOCK:
        current = _BOOTSTRAP_STATES.get(project_id)
        if current and current.get("status") == "BOOTSTRAPPING":
            return dict(current)
        _BOOTSTRAP_STATES[project_id] = {"status": "BOOTSTRAPPING", "message": "正在分析项目"}
    _BOOTSTRAP_EXECUTOR.submit(_run_bootstrap, project_id)
    return _runtime_bootstrap_state(project_id)


def _run_bootstrap(project_id: str) -> None:
    LOGGER.info("PROJECT_BOOTSTRAP_BACKGROUND START project_id=%s", project_id)
    try:
        with session_scope(_SESSION_FACTORY) as session:
            bootstrap = ProjectBootstrapService(session).bootstrap(project_id)
            state = {
                "status": "READY",
                "message": "项目分析完成",
                "readiness": _readiness_payload(bootstrap),
            }
    except Exception as exc:
        LOGGER.exception("PROJECT_BOOTSTRAP_BACKGROUND FAIL project_id=%s", project_id)
        state = {
            "status": "BOOTSTRAP_FAILED",
            "message": "项目分析失败，仍可进入工作台",
            "error": str(exc),
        }
    with _BOOTSTRAP_LOCK:
        _BOOTSTRAP_STATES[project_id] = state


def _runtime_bootstrap_state(project_id: str) -> dict[str, object]:
    with _BOOTSTRAP_LOCK:
        return dict(_BOOTSTRAP_STATES.get(project_id, {"status": "REGISTERED"}))


def _bootstrap_state(session, project_id: str) -> dict[str, object]:
    runtime = _runtime_bootstrap_state(project_id)
    if runtime.get("status") == "BOOTSTRAPPING":
        return runtime
    cached = _cached_ready_state(project_id)
    if cached is not None:
        return cached
    persisted = _persisted_ready_state(session, project_id)
    if persisted is not None:
        _remember_ready_state(project_id, persisted)
        return persisted
    return runtime


def get_project_bootstrap_state(project_id: str) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        return _bootstrap_state(session, project_id)


def is_project_context_ready(project_id: str) -> bool:
    return get_project_bootstrap_state(project_id).get("status") == "READY"


def _persisted_ready_state(session, project_id: str) -> dict[str, object] | None:
    project = session.get(Project, project_id)
    if project is None:
        return None
    revision = _quick_revision(project.root_path)
    if not revision:
        return None
    understanding = session.scalar(
        select(EngineeringKnowledge)
        .where(EngineeringKnowledge.project_id == project_id)
        .where(EngineeringKnowledge.knowledge_key == f"project-understanding:{revision[:12]}")
    )
    if understanding is None:
        return None
    return {
        "status": "READY",
        "message": "项目分析完成",
        "readiness": {
            "projectUnderstanding": True,
            "gitBaseline": {"revision": revision},
        },
    }


def _quick_revision(root_path: str) -> str | None:
    started = perf_counter()
    try:
        revision = GitService(root_path).base_revision()
        LOGGER.info(
            "project.quick_revision root=%s total_ms=%s",
            root_path,
            int((perf_counter() - started) * 1000),
        )
        return revision
    except Exception:
        LOGGER.exception("PROJECT_REOPEN quick revision failed root=%s", root_path)
        return None


def _cached_ready_state(project_id: str) -> dict[str, object] | None:
    cached = _BOOTSTRAP_READY_CACHE.get(project_id)
    if cached is None:
        return None
    cached_at, state = cached
    if perf_counter() - cached_at > _BOOTSTRAP_READY_CACHE_TTL_SECONDS:
        _BOOTSTRAP_READY_CACHE.pop(project_id, None)
        return None
    return dict(state)


def _remember_ready_state(project_id: str, state: dict[str, object]) -> None:
    _BOOTSTRAP_READY_CACHE[project_id] = (perf_counter(), dict(state))


def _choose_directory() -> Path | None:
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="选择本地 Git 仓库",
            mustexist=True,
        )
    finally:
        root.destroy()
    if not selected:
        return None
    return Path(selected).expanduser().resolve(strict=True)


def _readiness_payload(bootstrap) -> dict[str, object]:
    return {
        "projectUnderstanding": True,
        "fileInventory": {
            "files": bootstrap.file_count,
            "excluded": bootstrap.excluded_count,
        },
        "codeIndex": {
            "symbols": bootstrap.symbol_count,
            "relations": bootstrap.relation_count,
        },
        "gitBaseline": {
            "revision": bootstrap.revision,
            "modified": bootstrap.modified_count,
            "untracked": bootstrap.untracked_count,
        },
        "toolchain": {
            "kind": bootstrap.toolchain_kind,
            "testFrameworks": list(bootstrap.test_frameworks),
        },
    }


@router.get("/{project_id}/config")
def project_config(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(Project, project_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "secrets": "[redacted]"})


@router.get("/{project_id}/locks")
def lock_status(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(Project, project_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "status": "UNLOCKED"})


@router.get("/{project_id}/tasks")
def list_project_tasks(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(Project, project_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        tasks = [
            {
                "id": task.id,
                "projectId": task.project_id,
                "request": task.original_request,
                "status": task.status,
            }
            for task in session.query(ChangeTask)
            .filter(ChangeTask.project_id == project_id)
            .order_by(ChangeTask.created_at.desc())
        ]
    return ok({"projectId": project_id, "items": tasks})
