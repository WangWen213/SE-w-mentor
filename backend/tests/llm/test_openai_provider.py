from __future__ import annotations

from urllib import request as urlrequest
from typing import Any, cast

import pytest

from se_mentor.api import runtime
from se_mentor.security.secrets import Secret
from se_mentor.llm.base import (
    LLMRequest,
    ProviderHTTPError,
    ProviderInvalidResponse,
    ProviderTimeout,
)
from se_mentor.llm.openai_provider import OpenAIProviderConfig, OpenAIResponsesProvider


class FakeResponses:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeClient:
    def __init__(self, result: object) -> None:
        self.responses = FakeResponses(result)


class FakeUsage:
    input_tokens = 7
    output_tokens = 4


class FakeSDKResponse:
    output_text = "hello"
    usage = FakeUsage()


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


def test_T054_provider_maps_auth_rate_limit_timeout_and_records_usage() -> None:
    client = FakeClient(FakeSDKResponse())
    provider = OpenAIResponsesProvider(
        client=cast(Any, client),
        config=OpenAIProviderConfig(model="gpt-test", request_timeout_seconds=10),
    )
    response = provider.complete(
        LLMRequest(
            prompt_summary="structured change proposal",
            input_text="redacted input",
            response_schema={
                "title": "Draft",
                "type": "object",
                "properties": {
                    "goal": {"title": "Goal", "type": "string", "default": ""},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
        )
    )

    assert response.content == "hello"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 4
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["input"] == "redacted input"
    assert call["timeout"] == 10
    assert "response_schema" not in call
    assert call["text"] == {
        "format": {
            "type": "json_schema",
            "name": "structured_change_proposal",
            "schema": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
                "required": ["goal", "items"],
            },
            "strict": True,
        }
    }

    with pytest.raises(ProviderHTTPError) as auth_error:
        OpenAIResponsesProvider(
            client=cast(Any, FakeClient(FakeStatusError(401))),
            config=OpenAIProviderConfig(model="m"),
        ).complete(LLMRequest(prompt_summary="auth", input_text="x"))
    assert auth_error.value.code == "PROVIDER_HTTP_401"

    with pytest.raises(ProviderHTTPError) as rate_limit_error:
        OpenAIResponsesProvider(
            client=cast(Any, FakeClient(FakeStatusError(429))),
            config=OpenAIProviderConfig(model="m"),
        ).complete(LLMRequest(prompt_summary="rate", input_text="x"))
    assert rate_limit_error.value.code == "PROVIDER_HTTP_429"
    with pytest.raises(ProviderTimeout):
        OpenAIResponsesProvider(
            client=cast(Any, FakeClient(TimeoutError())),
            config=OpenAIProviderConfig(model="m"),
        ).complete(LLMRequest(prompt_summary="timeout", input_text="x"))
    with pytest.raises(ProviderInvalidResponse):
        OpenAIResponsesProvider(
            client=cast(Any, FakeClient(object())),
            config=OpenAIProviderConfig(model="m"),
        ).complete(LLMRequest(prompt_summary="invalid", input_text="x"))


def test_T054_http_provider_uses_bounded_timeout_and_classifies_urlopen_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SE_MENTOR_OPENAI_TIMEOUT", raising=False)
    assert runtime._openai_timeout_seconds() == 120

    monkeypatch.setenv("SE_MENTOR_OPENAI_TIMEOUT", "999")
    assert runtime._openai_timeout_seconds() == 180

    captured: dict[str, object] = {}

    def timeout_urlopen(request: urlrequest.Request, timeout: int) -> object:
        captured["timeout"] = timeout
        raise TimeoutError("timed out")

    monkeypatch.setenv("SE_MENTOR_OPENAI_TIMEOUT", "90")
    monkeypatch.setattr(runtime.urlrequest, "urlopen", timeout_urlopen)
    provider = runtime.build_openai_provider(
        Secret("sk-test"),
        config=runtime.ProviderRuntimeConfig(base_url="https://example.invalid/v1", model="gpt-test"),
    )

    with pytest.raises(ProviderTimeout, match="90s"):
        provider.complete(LLMRequest(prompt_summary="timeout", input_text="x"))
    assert captured["timeout"] == 90
