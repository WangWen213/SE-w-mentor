from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import (
    clear_provider_config,
    credential_status_payload,
    get_credential_store,
    set_provider_config,
)

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
    return ok(credential_status_payload(get_credential_store().status()))


@router.post("")
def set_credential(payload: CredentialSetRequest, response: Response) -> dict[str, object]:
    if not _is_supported_provider(payload.provider):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROVIDER_UNSUPPORTED", "only OpenAI provider is supported")
    set_provider_config(base_url=payload.base_url, model=payload.model)
    status_result = get_credential_store().set_api_key(payload.key)
    return ok(credential_status_payload(status_result))


@router.put("")
def update_credential(payload: CredentialUpdateRequest, response: Response) -> dict[str, object]:
    if not _is_supported_provider(payload.provider):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROVIDER_UNSUPPORTED", "only OpenAI provider is supported")
    set_provider_config(base_url=payload.base_url, model=payload.model)
    key = payload.key.strip() if payload.key else ""
    status_result = get_credential_store().update_api_key(key) if key else get_credential_store().status()
    return ok(credential_status_payload(status_result))


@router.delete("")
def clear_credential() -> dict[str, object]:
    clear_provider_config()
    return ok(credential_status_payload(get_credential_store().clear_api_key()))


def _is_supported_provider(provider: str) -> bool:
    return provider.strip().lower() in {"openai", "openai-compatible"}
