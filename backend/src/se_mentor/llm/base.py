from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
