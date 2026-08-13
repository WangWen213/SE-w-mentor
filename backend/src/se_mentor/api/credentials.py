from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import (
    ONLINE_SAFE_CREDENTIAL_ERROR,
    clear_provider_config,
    credential_status_payload,
    get_credential_store,
    get_runtime_settings,
    set_provider_config,
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
def status_credential() -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        return ok(credential_status_payload(None))
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return ok(credential_status_payload(None))
    return ok(credential_status_payload(get_credential_store().status()))


@router.post("")
def set_credential(payload: CredentialSetRequest, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CLOUD_DEMO_CREDENTIALS_DISABLED", "credentials are unavailable in demo mode")
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            ONLINE_SAFE_CREDENTIAL_ERROR,
            "online safe session credentials are not implemented yet",
        )
    if not _is_supported_provider(payload.provider):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROVIDER_UNSUPPORTED", "only OpenAI provider is supported")
    set_provider_config(base_url=payload.base_url, model=payload.model)
    status_result = get_credential_store().set_api_key(payload.key)
    return ok(credential_status_payload(status_result))


@router.put("")
def update_credential(payload: CredentialUpdateRequest, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        response.status_code = status.HTTP_409_CONFLICT
        return error("CLOUD_DEMO_CREDENTIALS_DISABLED", "credentials are unavailable in demo mode")
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(
            ONLINE_SAFE_CREDENTIAL_ERROR,
            "online safe session credentials are not implemented yet",
        )
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
def clear_credential() -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO:
        return ok(credential_status_payload(None))
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return ok(credential_status_payload(None))
    clear_provider_config()
    return ok(credential_status_payload(get_credential_store().clear_api_key()))


def _is_supported_provider(provider: str) -> bool:
    return provider.strip().lower() in {"openai", "openai-compatible"}
