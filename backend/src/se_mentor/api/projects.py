from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import (
    OnlineSessionUnavailable,
    current_online_session,
    online_owner_hash,
    online_project_filter,
    require_project_access,
)
from se_mentor.api.runtime import (
    ONLINE_SAFE_WORKSPACE_ERROR,
    get_online_workspace_factory,
    get_runtime_settings,
    get_session_factory,
)
from se_mentor.db.session import session_scope
from se_mentor.git.git_service import GitService
from se_mentor.models.knowledge import EngineeringKnowledge
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask
from se_mentor.projects.bootstrap import ProjectBootstrapService
from se_mentor.projects.project_repository import find_project_by_root
from se_mentor.projects.project_service import ProjectRegistrationError, register_project
from se_mentor.runtime.demo import DemoRuntimeError, ensure_demo_workspace
from se_mentor.runtime.online_workspaces import (
    ONLINE_SAFE_USER_PATH_ERROR,
    ONLINE_SAFE_WORKSPACE_LIMIT_ERROR,
    OnlineWorkspaceError,
)
from se_mentor.runtime.profiles import RuntimeProfile

router = APIRouter(prefix="/api/projects", tags=["projects"])
_SESSION_FACTORY = get_session_factory()
LOGGER = logging.getLogger("se_mentor.api.projects")
ONLINE_SAFE_PROJECT_ZIP_REQUIRED = "ONLINE_SAFE_PROJECT_ZIP_REQUIRED"
ONLINE_SAFE_PATCH_EXPORT_UNTRACKED_ERROR = "ONLINE_SAFE_PATCH_EXPORT_UNTRACKED_UNSUPPORTED"
_BOOTSTRAP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="project-bootstrap")
_BOOTSTRAP_LOCK = Lock()
_BOOTSTRAP_STATES: dict[str, dict[str, object]] = {}
_BOOTSTRAP_READY_CACHE_TTL_SECONDS = 3.0
_BOOTSTRAP_READY_CACHE: dict[str, tuple[float, dict[str, object]]] = {}


class ProjectCreate(BaseModel):
    root_path: str | None = Field(default=None, alias="rootPath")


@router.get("")
def list_projects(request: Request, response: Response) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        projects = session.scalars(
            online_project_filter(
                select(Project).order_by(Project.updated_at.desc()),
                request,
                response,
            )
        ).all()
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
def create_project(
    payload: ProjectCreate,
    request: Request,
    response: Response,
) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if payload.root_path and payload.root_path.strip():
            response.status_code = status.HTTP_409_CONFLICT
            return error(
                ONLINE_SAFE_USER_PATH_ERROR,
                "online safe projects must be imported from a ZIP upload",
            )
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_PROJECT_ZIP_REQUIRED, "upload a project ZIP first")
    if not payload.root_path or not payload.root_path.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROJECT_PATH_REQUIRED", "project rootPath is required")
    return _register_project(payload.root_path, response)


@router.post("/choose-local", status_code=status.HTTP_201_CREATED)
def choose_local_project(request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_PROJECT_ZIP_REQUIRED, "upload a project ZIP first")
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            "CLOUD_DEMO_PROJECT_RESTRICTED",
            "demo mode only allows the predefined demo workspace",
        )
    LOGGER.info("PROJECT_CHOOSE_LOCAL START")
    selected = _choose_directory()
    if selected is None:
        LOGGER.info("PROJECT_CHOOSE_LOCAL CANCEL")
        response.status_code = status.HTTP_409_CONFLICT
        return error("PROJECT_SELECTION_CANCELLED", "project selection was cancelled")
    LOGGER.info("PROJECT_CHOOSE_LOCAL SELECTED path=%s", selected)
    return _register_project(str(selected), response)


def _register_project(root_path: str, response: Response) -> dict[str, object]:
    settings = get_runtime_settings()
    if settings.profile is RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            ONLINE_SAFE_WORKSPACE_ERROR,
            "online safe workspace sessions are not implemented yet",
        )
    if settings.profile is RuntimeProfile.CLOUD_DEMO:
        try:
            demo_root = ensure_demo_workspace(settings.demo_workspace_root)
            requested_root = Path(root_path).expanduser().resolve(strict=True)
        except (OSError, DemoRuntimeError):
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error(
                "CLOUD_DEMO_PROJECT_RESTRICTED",
                "demo mode only allows the predefined demo workspace",
            )
        if requested_root != demo_root:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error(
                "CLOUD_DEMO_PROJECT_RESTRICTED",
                "demo mode only allows the predefined demo workspace",
            )
        root_path = str(demo_root)
    LOGGER.info(
        "PROJECT_REGISTER START root=%s",
        "[cloud-demo-workspace]" if settings.profile is RuntimeProfile.CLOUD_DEMO else root_path,
    )
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


@router.post("/import-zip", status_code=status.HTTP_201_CREATED)
async def import_project_zip(request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            "PROJECT_ZIP_IMPORT_UNAVAILABLE",
            "project ZIP import is only available in ONLINE_SAFE",
        )
    try:
        online_session = current_online_session(request, response)
        owner_hash = online_owner_hash(online_session.session_id)
    except OnlineSessionUnavailable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return error("ONLINE_SAFE_SESSION_LIMIT_REACHED", "active session limit reached")
    existing = _online_project_for_owner(owner_hash)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return ok(
            _project_payload(existing, bootstrap=get_project_bootstrap_state(existing.id))
        )
    archive = await request.body()
    archive_name = request.headers.get("x-se-mentor-filename", "project.zip")
    try:
        workspace = get_online_workspace_factory().import_zip(
            online_session,
            archive,
            archive_name=archive_name,
        )
    except OnlineWorkspaceError as exc:
        response.status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if exc.code == ONLINE_SAFE_WORKSPACE_LIMIT_ERROR
            else status.HTTP_400_BAD_REQUEST
        )
        return error(exc.code, str(exc))
    with session_scope(_SESSION_FACTORY) as session:
        try:
            registered = register_project(
                session,
                workspace.root,
                authorized_root=workspace.root,
            )
        except ProjectRegistrationError as exc:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error("PROJECT_REGISTRATION_FAILED", str(exc))
        project = registered.project
        project.owner_session_hash = owner_hash
        project_payload = _project_payload(project, bootstrap={"status": "REGISTERED"})
        project_payload["revision"] = registered.current_revision
        project_id = project.id
    project_payload["bootstrap"] = _schedule_bootstrap(project_id)
    return ok(project_payload)


@router.get("/{project_id}/export.zip")
def export_project_zip(
    project_id: str,
    request: Request,
    response: Response,
):
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            "PROJECT_ZIP_EXPORT_UNAVAILABLE",
            "project ZIP export is only available in ONLINE_SAFE",
        )
    project = _require_online_project(project_id, request, response)
    if project is None:
        return error("PROJECT_NOT_FOUND", "project not found")
    try:
        handle = _current_project_workspace(project, request, response)
        archive = get_online_workspace_factory().export_zip(handle)
    except OnlineWorkspaceError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error(exc.code, str(exc))
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="se-mentor-project.zip"'},
    )


@router.get("/{project_id}/changes.patch")
def export_project_patch(
    project_id: str,
    request: Request,
    response: Response,
):
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            "PROJECT_PATCH_EXPORT_UNAVAILABLE",
            "project patch export is only available in ONLINE_SAFE",
        )
    project = _require_online_project(project_id, request, response)
    if project is None:
        return error("PROJECT_NOT_FOUND", "project not found")
    try:
        _current_project_workspace(project, request, response)
        git = GitService(project.root_path)
        git_status = git.status()
        if git_status.untracked:
            response.status_code = status.HTTP_409_CONFLICT
            return error(
                ONLINE_SAFE_PATCH_EXPORT_UNTRACKED_ERROR,
                "patch export only supports tracked file changes; download ZIP for created files",
            )
        patch = git.scoped_diff(list(git_status.modified)) if git_status.modified else ""
    except Exception as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error("PROJECT_PATCH_EXPORT_FAILED", str(exc))
    return Response(
        content=patch,
        media_type="text/x-patch; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="se-mentor-changes.patch"'},
    )


@router.get("/{project_id}")
def get_project(project_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        project = require_project_access(session, project_id, request, response)
        if project is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        return ok(_project_payload(project, bootstrap=_bootstrap_state(session, project.id)))


def _project_payload(project: Project, *, bootstrap: dict[str, object]) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return {
            "id": project.id,
            "authorized": True,
            "rootPath": "Uploaded Project",
            "name": "Uploaded Project",
            "bootstrap": bootstrap,
        }
    return {
        "id": project.id,
        "authorized": True,
        "rootPath": project.root_path,
        "bootstrap": bootstrap,
    }


@router.get("/{project_id}/bootstrap")
def bootstrap_status(project_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if require_project_access(session, project_id, request, response) is None:
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
def project_config(project_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if require_project_access(session, project_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "secrets": "[redacted]"})


@router.get("/{project_id}/locks")
def lock_status(project_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if require_project_access(session, project_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
    return ok({"projectId": project_id, "status": "UNLOCKED"})


@router.get("/{project_id}/tasks")
def list_project_tasks(project_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if require_project_access(session, project_id, request, response) is None:
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


def _online_project_for_owner(owner_hash: str) -> Project | None:
    with session_scope(_SESSION_FACTORY) as session:
        project = session.scalar(
            select(Project)
            .where(Project.owner_session_hash == owner_hash)
            .order_by(Project.created_at.asc())
        )
        if project is None:
            return None
        project.updated_at = datetime.now(UTC)
        session.flush()
        session.expunge(project)
        return project


def _require_online_project(
    project_id: str,
    request: Request,
    response: Response,
) -> Project | None:
    with session_scope(_SESSION_FACTORY) as session:
        project = require_project_access(session, project_id, request, response)
        if project is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return None
        session.expunge(project)
        return project


def _current_project_workspace(
    project: Project,
    request: Request,
    response: Response,
):
    try:
        online_session = current_online_session(request, response)
        handle = get_online_workspace_factory().get_or_create(online_session)
    except OnlineSessionUnavailable as exc:
        raise OnlineWorkspaceError(
            "ONLINE_SAFE_SESSION_LIMIT_REACHED",
            "active session limit reached",
        ) from exc
    if Path(project.root_path).resolve() != handle.root.resolve():
        raise OnlineWorkspaceError(
            "ONLINE_SAFE_WORKSPACE_PROJECT_MISMATCH",
            "project does not belong to the current session workspace",
        )
    return handle
