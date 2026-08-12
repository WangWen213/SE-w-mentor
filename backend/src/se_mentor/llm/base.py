from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(RuntimeError):
    code = "PROVIDER_ERROR"


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderCancelled(ProviderError):
    code = "PROVIDER_CANCELLED"


class ProviderAuthError(ProviderError):
    code = "PROVIDER_AUTH"


class ProviderRateLimitError(ProviderError):
    code = "PROVIDER_RATE_LIMIT"


class ProviderInvalidResponse(ProviderError):
    code = "PROVIDER_INVALID_RESPONSE"


class ProviderRequestError(ProviderError):
    code = "PROVIDER_REQUEST_FAILED"


class ProviderHTTPError(ProviderRequestError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def code(self) -> str:
        return f"PROVIDER_HTTP_{self.status_code}"


class ProviderConnectionError(ProviderRequestError):
    code = "PROVIDER_CONNECTION_ERROR"


class ProviderConfigError(ProviderError):
    code = "PROVIDER_CONFIG_INVALID"


class ProviderRequestBuildError(ProviderError):
    code = "PROVIDER_REQUEST_BUILD_FAILED"


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMRequest:
    prompt_summary: str
    input_text: str
    timeout_seconds: float | None = None
    cancellation_token: str | None = None
    response_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: LLMUsage
    model: str
    provider: str


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...
