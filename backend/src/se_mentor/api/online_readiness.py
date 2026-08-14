from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request, Response, status
from sqlalchemy.orm import Session

from se_mentor.api.envelope import error
from se_mentor.api.online_access import require_project_access
from se_mentor.api.runtime import (
    ONLINE_SAFE_HTTPS_ERROR,
    ONLINE_SAFE_PROVIDER_ERROR,
    ONLINE_SAFE_SESSION_ERROR,
    ONLINE_SAFE_SESSION_EXPIRED_ERROR,
    ONLINE_SAFE_WORKSPACE_ERROR,
    OnlineSafeNotReadyError,
    get_online_session_provider,
    get_online_session_store,
    get_online_workspace_factory,
    get_runtime_settings,
)
from se_mentor.llm.base import LLMProvider
from se_mentor.runtime.online_provider_security import (
    ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED,
)
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    OnlineSessionExpired,
    OnlineSessionRequired,
)
from se_mentor.runtime.online_workspaces import OnlineWorkspaceError
from se_mentor.runtime.profiles import RuntimeProfile

ONLINE_SAFE_PROJECT_NOT_READY = "ONLINE_SAFE_PROJECT_NOT_READY"


@dataclass(frozen=True)
class OnlineSafeReadiness:
    provider: LLMProvider
    session_id: str


def is_secure_online_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if not get_runtime_settings().trust_proxy:
        return False
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return forwarded_proto.strip().lower() == "https"


def online_safe_insecure_error(
    request: Request,
    response: Response,
    *,
    message: str,
) -> dict[str, object] | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return None
    if is_secure_online_request(request):
        return None
    response.status_code = status.HTTP_409_CONFLICT
    return error(ONLINE_SAFE_HTTPS_ERROR, message)


def require_online_safe_provider(
    request: Request,
    response: Response,
) -> OnlineSafeReadiness | dict[str, object]:
    insecure = online_safe_insecure_error(
        request,
        response,
        message="ONLINE_SAFE requests require HTTPS",
    )
    if insecure is not None:
        return insecure
    session_id = request.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    try:
        get_online_session_store().require(session_id)
        provider = get_online_session_provider(session_id)
    except OnlineSessionRequired:
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_SESSION_ERROR, "online safe session is required")
    except OnlineSessionExpired:
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_SESSION_EXPIRED_ERROR, "online safe session expired")
    except OnlineSafeNotReadyError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error(str(exc), _online_safe_not_ready_message(str(exc)))
    return OnlineSafeReadiness(provider=provider, session_id=session_id or "")


def require_online_safe_project_readiness(
    db: Session,
    project_id: str,
    request: Request,
    response: Response,
) -> OnlineSafeReadiness | dict[str, object]:
    readiness = require_online_safe_provider(request, response)
    if isinstance(readiness, dict):
        return readiness
    project = require_project_access(db, project_id, request, response)
    if project is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROJECT_NOT_FOUND", "project not found")
    try:
        session = get_online_session_store().require(readiness.session_id)
        handle = get_online_workspace_factory().get_or_create(session)
    except (OnlineSessionRequired, OnlineSessionExpired):
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_SESSION_ERROR, "online safe session is required")
    except OnlineWorkspaceError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error(exc.code, str(exc))
    if project.root_path != str(handle.root):
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            ONLINE_SAFE_WORKSPACE_ERROR,
            "online safe project is not bound to the current session workspace",
        )
    return readiness


def _online_safe_not_ready_message(code: str) -> str:
    if code == ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED:
        return "online safe provider credential is required"
    if code == ONLINE_SAFE_PROVIDER_ERROR:
        return "online safe provider is not ready"
    return "online safe request is not ready"
