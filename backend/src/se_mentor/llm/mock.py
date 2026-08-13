from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.llm.base import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderCancelled,
    ProviderTimeout,
)
from se_mentor.models.llm import LLMCall, LLMCallStatus, ParseStatus


@dataclass(frozen=True)
class MockResponse:
    match: str
    content: str
    input_tokens: int
    output_tokens: int
    min_call: int = 1


class MockLLMProvider:
    provider_name = "mock"

    def __init__(
        self,
        *,
        model: str,
        script: tuple[MockResponse, ...],
        timeout_after_calls: int | None = None,
        cancelled: bool = False,
    ) -> None:
        self.model = model
        self.script = script
        self.timeout_after_calls = timeout_after_calls
        self.cancelled = cancelled
        self.calls = 0

    def reset(self) -> MockLLMProvider:
        self.calls = 0
        return self

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.cancelled:
            raise ProviderCancelled("mock provider cancelled")
        if self.timeout_after_calls is not None and self.calls >= self.timeout_after_calls:
            raise ProviderTimeout("mock provider timeout")
        self.calls += 1
        for response in self.script:
            if self.calls < response.min_call:
                continue
            if response.match in request.input_text or response.match in request.prompt_summary:
                return LLMResponse(
                    content=response.content,
                    usage=LLMUsage(response.input_tokens, response.output_tokens),
                    model=self.model,
                    provider=self.provider_name,
                )
        raise KeyError("undefined mock call")

    def record_usage(
        self,
        session: Session,
        *,
        iteration_id: str,
        response: LLMResponse,
        request_summary: str,
    ) -> LLMCall:
        call = LLMCall(
            iteration_id=iteration_id,
            provider_name=self.provider_name,
            model_name=self.model,
            request_summary=request_summary,
            response_summary=f"{len(response.content)} chars",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            compression_count=0,
            status=LLMCallStatus.SUCCESS,
            retry_count=0,
            latency_ms=None,
            error_code=None,
            parse_status=ParseStatus.VALID,
        )
        session.add(call)
        session.flush()
        return call
