from __future__ import annotations

import pytest

from se_mentor.llm.base import (
    LLMRequest,
    ProviderAuthError,
    ProviderInvalidResponse,
    ProviderRateLimitError,
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


class FakeSDKResponse:
    output_text = "hello"
    usage = {"input_tokens": 7, "output_tokens": 4}


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


def test_T054_provider_maps_auth_rate_limit_timeout_and_records_usage() -> None:
    client = FakeClient(FakeSDKResponse())
    provider = OpenAIResponsesProvider(
        client=client,
        config=OpenAIProviderConfig(model="gpt-test", request_timeout_seconds=10),
    )
    response = provider.complete(LLMRequest(prompt_summary="summary", input_text="redacted input"))

    assert response.content == "hello"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 4
    assert client.responses.calls == [
        {"model": "gpt-test", "input": "redacted input", "timeout": 10}
    ]

    with pytest.raises(ProviderAuthError):
        OpenAIResponsesProvider(client=FakeClient(FakeStatusError(401)), config=OpenAIProviderConfig(model="m")).complete(
            LLMRequest(prompt_summary="auth", input_text="x")
        )
    with pytest.raises(ProviderRateLimitError):
        OpenAIResponsesProvider(client=FakeClient(FakeStatusError(429)), config=OpenAIProviderConfig(model="m")).complete(
            LLMRequest(prompt_summary="rate", input_text="x")
        )
    with pytest.raises(ProviderTimeout):
        OpenAIResponsesProvider(client=FakeClient(TimeoutError()), config=OpenAIProviderConfig(model="m")).complete(
            LLMRequest(prompt_summary="timeout", input_text="x")
        )
    with pytest.raises(ProviderInvalidResponse):
        OpenAIResponsesProvider(client=FakeClient(object()), config=OpenAIProviderConfig(model="m")).complete(
            LLMRequest(prompt_summary="invalid", input_text="x")
        )
