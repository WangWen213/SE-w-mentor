from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import (
    ONLINE_SAFE_HTTPS_ERROR,
    ONLINE_SAFE_WORKSPACE_ERROR,
    get_online_session_store,
    get_online_workspace_factory,
    get_runtime_settings,
)
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    OnlineSession,
    OnlineSessionLimitExceeded,
)
from se_mentor.runtime.online_workspaces import OnlineWorkspaceError, WorkspaceHandle
from se_mentor.runtime.profiles import RuntimeProfile

router = APIRouter(prefix="/api/runtime/workspace", tags=["runtime-workspace"])


@router.get("")
def get_runtime_workspace(request: Request, response: Response) -> dict[str, object]:
    if not _online_safe(response):
        return error(ONLINE_SAFE_WORKSPACE_ERROR, "online safe workspace is unavailable")
    try:
        session = get_online_session_store().get_or_create(_session_cookie(request))
        _cleanup_expired_workspaces()
        handle = get_online_workspace_factory().get_or_create(session)
    except OnlineSessionLimitExceeded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return error("ONLINE_SAFE_SESSION_LIMIT_REACHED", "active session limit reached")
    except OnlineWorkspaceError as exc:
        response.status_code = _workspace_status(exc)
        return error(exc.code, str(exc))
    _set_session_cookie(response, session)
    return ok(_workspace_payload(handle))


@router.post("/reset")
def reset_runtime_workspace(request: Request, response: Response) -> dict[str, object]:
    if not _online_safe(response):
        return error(ONLINE_SAFE_WORKSPACE_ERROR, "online safe workspace is unavailable")
    if request.url.scheme != "https":
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_HTTPS_ERROR, "ONLINE_SAFE workspace reset requires HTTPS")
    try:
        session = get_online_session_store().get_or_create(_session_cookie(request))
        _cleanup_expired_workspaces()
        handle = get_online_workspace_factory().reset_current_workspace(session)
    except OnlineSessionLimitExceeded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return error("ONLINE_SAFE_SESSION_LIMIT_REACHED", "active session limit reached")
    except OnlineWorkspaceError as exc:
        response.status_code = _workspace_status(exc)
        return error(exc.code, str(exc))
    _set_session_cookie(response, session)
    return ok(_workspace_payload(handle))


def _online_safe(response: Response) -> bool:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return True
    response.status_code = status.HTTP_409_CONFLICT
    return False


def _cleanup_expired_workspaces() -> None:
    get_online_workspace_factory().cleanup_expired(
        get_online_session_store().active_session_ids()
    )


def _session_cookie(request: Request) -> str | None:
    return request.cookies.get(ONLINE_SESSION_COOKIE_NAME)


def _set_session_cookie(response: Response, session: OnlineSession) -> None:
    response.set_cookie(
        key=ONLINE_SESSION_COOKIE_NAME,
        value=session.session_id,
        max_age=get_online_session_store().ttl_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _workspace_payload(handle: WorkspaceHandle) -> dict[str, object]:
    return {
        "ready": True,
        "workspace": {
            "id": handle.identifier,
            "baseline": handle.baseline_name,
            "baselineRevision": handle.baseline_revision,
        },
    }


def _workspace_status(exc: OnlineWorkspaceError) -> int:
    if exc.code.endswith("_LIMIT_EXCEEDED"):
        return status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    if exc.code.endswith("_INVALID") or exc.code.endswith("_VIOLATION"):
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_409_CONFLICT
