from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from typing import Any, Protocol

from se_mentor.llm.base import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderInvalidResponse,
    ProviderRequestBuildError,
    ProviderRequestError,
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
            raw = self.client.responses.create(**self._request_kwargs(request))
        except TimeoutError as exc:
            raise ProviderTimeout("OpenAI provider timeout") from exc
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            if "timeout" in type(exc).__name__.lower():
                raise ProviderTimeout(f"OpenAI provider timeout: {_safe_error_detail(exc)}") from exc
            status_code = _status_code(exc)
            detail = _safe_error_detail(exc)
            if isinstance(status_code, int):
                raise ProviderHTTPError(status_code, f"OpenAI HTTP {status_code}: {detail}") from exc
            if _is_connection_error(exc):
                raise ProviderConnectionError(f"OpenAI connection error: {detail}") from exc
            raise ProviderRequestError(f"OpenAI provider request failed: {detail}") from exc
        content = getattr(raw, "output_text", None)
        usage = getattr(raw, "usage", None)
        if not isinstance(content, str) or usage is None:
            raise ProviderInvalidResponse("OpenAI response missing text or usage")
        input_tokens = _int_usage(usage, "input_tokens")
        output_tokens = _int_usage(usage, "output_tokens")
        return LLMResponse(
            content=content,
            usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model=self.config.model,
            provider=self.provider_name,
        )

    def _request_kwargs(self, request: LLMRequest) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self.config.model,
            "input": request.input_text,
            "timeout": request.timeout_seconds or self.config.request_timeout_seconds,
        }
        if request.response_schema is None:
            return kwargs
        try:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _schema_name(request.prompt_summary),
                    "schema": _strict_json_schema(request.response_schema),
                    "strict": True,
                },
            }
        except Exception as exc:
            raise ProviderRequestBuildError(f"OpenAI structured output request build failed: {exc}") from exc
        return kwargs


def _int_usage(usage: object, key: str) -> int:
    value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
    if not isinstance(value, int) or value < 0:
        raise ProviderInvalidResponse(f"OpenAI usage missing {key}")
    return value


def _schema_name(prompt_summary: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", prompt_summary.strip()).strip("_")
    return name[:64] or "structured_response"


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(schema)
    _normalize_schema_node(normalized)
    return normalized


def _normalize_schema_node(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _normalize_schema_node(item)
        return
    if not isinstance(node, dict):
        return
    node.pop("default", None)
    node.pop("title", None)
    properties = node.get("properties")
    if isinstance(properties, dict):
        node["additionalProperties"] = False
        node["required"] = list(properties.keys())
    for value in node.values():
        _normalize_schema_node(value)


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    return response_status_code if isinstance(response_status_code, int) else None


def _is_connection_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return any(token in name for token in ("connection", "connect", "network", "apierror"))


def _safe_error_detail(exc: Exception) -> str:
    raw = str(exc).strip() or type(exc).__name__
    redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", raw)
    redacted = re.sub(r"(?i)(authorization|api[-_ ]?key|bearer)\s*[:=]\s*\S+", r"\1: ***", redacted)
    redacted = re.sub(r"\s+", " ", redacted).strip()
    return f"{type(exc).__name__}: {redacted[:360]}"
