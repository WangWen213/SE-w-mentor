from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.context.context_builder import ContextPackage
from se_mentor.llm.base import LLMProvider, LLMRequest, LLMResponse
from se_mentor.models.task import ChangeTask, TaskStatus


class TokenBudgetPaused(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenBudgetEstimate:
    input_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    max_total_tokens: int

    @property
    def required_tokens(self) -> int:
        return self.input_tokens + self.reserved_output_tokens + self.safety_margin_tokens

    @property
    def over_budget(self) -> bool:
        return self.required_tokens > self.max_total_tokens


class BudgetedLLMProvider:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def complete(
        self,
        *,
        task_id: str,
        context_package: ContextPackage,
        request: LLMRequest,
        max_total_tokens: int,
        reserved_output_tokens: int,
        safety_margin_tokens: int,
    ) -> LLMResponse:
        prompt = f"{context_package.render()}\n\n{request.input_text}"
        estimate = TokenBudgetEstimate(
            input_tokens=estimate_tokens(prompt),
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            max_total_tokens=max_total_tokens,
        )
        if estimate.over_budget:
            self._pause_task(task_id, estimate)
            raise TokenBudgetPaused(
                f"token budget exceeded: required={estimate.required_tokens} max={max_total_tokens}"
            )
        return self.provider.complete(
            LLMRequest(
                prompt_summary=request.prompt_summary,
                input_text=prompt,
                response_schema=request.response_schema,
                timeout_seconds=request.timeout_seconds,
                cancellation_token=request.cancellation_token,
            )
        )

    def _pause_task(self, task_id: str, estimate: TokenBudgetEstimate) -> None:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        task.status = TaskStatus.PAUSED
        task.failure_code = "TOKEN_BUDGET_EXCEEDED"
        task.failure_message = (
            f"required={estimate.required_tokens}, max={estimate.max_total_tokens}, "
            f"input={estimate.input_tokens}, reserved_output={estimate.reserved_output_tokens}, "
            f"safety_margin={estimate.safety_margin_tokens}"
        )
        self.session.flush()


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
