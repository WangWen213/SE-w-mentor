from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import (
    ONLINE_SAFE_HTTPS_ERROR,
    ONLINE_SAFE_SESSION_ERROR,
    ONLINE_SAFE_SESSION_EXPIRED_ERROR,
    clear_provider_config,
    credential_status_payload,
    get_credential_store,
    get_online_session_store,
    get_runtime_settings,
    set_provider_config,
)
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    OnlineCredentialValidationError,
    OnlineSession,
    OnlineSessionExpired,
    OnlineSessionLimitExceeded,
    OnlineSessionRequired,
)
from se_mentor.runtime.profiles import RuntimeProfile

router = APIRouter(prefix="/api/credentials/llm", tags=["credentials"])


class CredentialSetRequest(BaseModel):
    provider: str = "OpenAI"
    key: str = Field(min_length=1)
    base_url: str = Field(min_length=1, alias="baseUrl")
    model: str = Field(min_length=1)


class CredentialUpdateRequest(BaseModel):
    provider: str = "OpenAI"
    key: str | None = None
    base_url: str = Field(min_length=1, alias="baseUrl")
    model: str = Field(min_length=1)


@router.get("/status")
def status_credential(request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        return ok(credential_status_payload(None))
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        try:
            session = get_online_session_store().get_or_create(_session_cookie(request))
        except OnlineSessionLimitExceeded:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return error("ONLINE_SAFE_SESSION_LIMIT_REACHED", "active session limit reached")
        _set_session_cookie(response, session)
        return ok(_online_session_status_payload(session))
    return ok(credential_status_payload(get_credential_store().status()))


@router.post("")
def set_credential(
    payload: CredentialSetRequest,
    request: Request,
    response: Response,
) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CLOUD_DEMO_CREDENTIALS_DISABLED", "credentials are unavailable in demo mode")
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if insecure := _online_safe_insecure_error(request, response):
            return insecure
        try:
            session = get_online_session_store().set_credential(
                _session_cookie(request),
                provider=payload.provider,
                base_url=payload.base_url,
                model=payload.model,
                key=payload.key,
            )
        except OnlineCredentialValidationError as exc:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error("PROVIDER_UNSUPPORTED", str(exc))
        except OnlineSessionRequired:
            response.status_code = status.HTTP_409_CONFLICT
            return error(ONLINE_SAFE_SESSION_ERROR, "online safe session is required")
        except OnlineSessionExpired:
            response.status_code = status.HTTP_409_CONFLICT
            return error(ONLINE_SAFE_SESSION_EXPIRED_ERROR, "online safe session expired")
        _set_session_cookie(response, session)
        return ok(_online_session_status_payload(session))
    if not _is_supported_provider(payload.provider):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROVIDER_UNSUPPORTED", "only OpenAI provider is supported")
    set_provider_config(base_url=payload.base_url, model=payload.model)
    status_result = get_credential_store().set_api_key(payload.key)
    return ok(credential_status_payload(status_result))


@router.put("")
def update_credential(
    payload: CredentialUpdateRequest,
    request: Request,
    response: Response,
) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CLOUD_DEMO_CREDENTIALS_DISABLED", "credentials are unavailable in demo mode")
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if insecure := _online_safe_insecure_error(request, response):
            return insecure
        try:
            session = get_online_session_store().update_credential(
                _session_cookie(request),
                provider=payload.provider,
                base_url=payload.base_url,
                model=payload.model,
                key=payload.key,
            )
        except OnlineCredentialValidationError as exc:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error("PROVIDER_UNSUPPORTED", str(exc))
        except OnlineSessionRequired:
            response.status_code = status.HTTP_409_CONFLICT
            return error(ONLINE_SAFE_SESSION_ERROR, "online safe session credential is required")
        except OnlineSessionExpired:
            response.status_code = status.HTTP_409_CONFLICT
            return error(ONLINE_SAFE_SESSION_EXPIRED_ERROR, "online safe session expired")
        _set_session_cookie(response, session)
        return ok(_online_session_status_payload(session))
    if not _is_supported_provider(payload.provider):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROVIDER_UNSUPPORTED", "only OpenAI provider is supported")
    set_provider_config(base_url=payload.base_url, model=payload.model)
    key = payload.key.strip() if payload.key else ""
    status_result = (
        get_credential_store().update_api_key(key)
        if key
        else get_credential_store().status()
    )
    return ok(credential_status_payload(status_result))


@router.delete("")
def clear_credential(request: Request, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        return ok(credential_status_payload(None))
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        if insecure := _online_safe_insecure_error(request, response):
            return insecure
        try:
            session = get_online_session_store().clear_credential(_session_cookie(request))
        except OnlineSessionLimitExceeded:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return error("ONLINE_SAFE_SESSION_LIMIT_REACHED", "active session limit reached")
        _set_session_cookie(response, session)
        return ok(_online_session_status_payload(session))
    clear_provider_config()
    return ok(credential_status_payload(get_credential_store().clear_api_key()))


def _is_supported_provider(provider: str) -> bool:
    return provider.strip().lower() in {"openai", "openai-compatible"}


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


def _online_session_status_payload(session: OnlineSession) -> dict[str, object]:
    credential = session.credential
    return {
        "configured": credential is not None,
        "provider": credential.metadata.provider if credential is not None else "OpenAI",
        "source": "ONLINE_SAFE_SESSION",
        "profile": RuntimeProfile.ONLINE_SAFE.value,
        "baseUrl": credential.metadata.base_url if credential is not None else None,
        "model": credential.metadata.model if credential is not None else None,
    }


def _online_safe_insecure_error(
    request: Request,
    response: Response,
) -> dict[str, object] | None:
    if is_secure_online_request(request):
        return None
    response.status_code = status.HTTP_409_CONFLICT
    return error(ONLINE_SAFE_HTTPS_ERROR, "ONLINE_SAFE credential writes require HTTPS")


def is_secure_online_request(request: Request) -> bool:
    return request.url.scheme == "https"
