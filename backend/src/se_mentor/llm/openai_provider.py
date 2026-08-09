from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from se_mentor.llm.base import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderAuthError,
    ProviderInvalidResponse,
    ProviderRateLimitError,
    ProviderTimeout,
)


class _ResponsesClient(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesClient


@dataclass(frozen=True)
class OpenAIProviderConfig:
    model: str
    request_timeout_seconds: int = 60


class OpenAIResponsesProvider:
    provider_name = "openai"

    def __init__(self, *, client: _OpenAIClient, config: OpenAIProviderConfig) -> None:
        self.client = client
        self.config = config
        self.model = config.model

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            raw = self.client.responses.create(
                model=self.config.model,
                input=request.input_text,
                timeout=request.timeout_seconds or self.config.request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderTimeout("OpenAI provider timeout") from exc
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code == 401:
                raise ProviderAuthError("OpenAI authentication failed") from exc
            if status_code == 429:
                raise ProviderRateLimitError("OpenAI rate limit") from exc
            raise
        content = getattr(raw, "output_text", None)
        usage = getattr(raw, "usage", None)
        if not isinstance(content, str) or not isinstance(usage, dict):
            raise ProviderInvalidResponse("OpenAI response missing text or usage")
        input_tokens = _int_usage(usage, "input_tokens")
        output_tokens = _int_usage(usage, "output_tokens")
        return LLMResponse(
            content=content,
            usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model=self.config.model,
            provider=self.provider_name,
        )


def _int_usage(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key)
    if not isinstance(value, int) or value < 0:
        raise ProviderInvalidResponse(f"OpenAI usage missing {key}")
    return value
