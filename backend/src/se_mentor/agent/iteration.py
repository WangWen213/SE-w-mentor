from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from se_mentor.agent.action_parser import AgentActionParser, ParseOutcome
from se_mentor.context.context_builder import ContextBuilder, ContextItem, TrustLabel
from se_mentor.context.token_budget import BudgetedLLMProvider, estimate_tokens
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.models.governance import GovernanceVerdict
from se_mentor.models.llm import (
    AgentAction,
    AgentActionStatus,
    LLMCall,
    LLMCallStatus,
    ParseStatus,
    RiskLevel,
)
from se_mentor.models.task import (
    ChangeTask,
    TaskIteration,
    TaskIterationPhase,
    TaskIterationResult,
)
from se_mentor.tools.dispatcher import ToolDispatcher, ToolDispatchResult
from se_mentor.tools.registry import ToolRegistry


@dataclass(frozen=True)
class IterationResult:
    iteration_id: str
    action_id: str | None
    tool_result: ToolDispatchResult | None
    paused: bool


class SingleTurnAgentRunner:
    def __init__(
        self,
        session: Session,
        *,
        project_root: str | Path,
        context_builder: ContextBuilder,
        provider: LLMProvider,
        registry: ToolRegistry,
        tool_handlers: dict[str, Callable[[Any], object]],
    ) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()
        self.context_builder = context_builder
        self.provider = provider
        self.registry = registry
        self.tool_handlers = tool_handlers

    def run(
        self,
        *,
        task_id: str,
        proposal_hash: str,
        revision: str,
        goal: str,
    ) -> IterationResult:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        iteration = self._create_iteration(task_id)
        context = self.context_builder.build(
            goal=goal,
            governance_items=(
                ContextItem(
                    "governance", "governance", "governance required", 100, TrustLabel.SYSTEM
                ),
            ),
            execution_policy=ContextItem("policy", "policy", "finite scope", 95, TrustLabel.SYSTEM),
            current_error=ContextItem("feedback", "feedback", "none", 90, TrustLabel.TOOL_OUTPUT),
            repository_items=(),
            knowledge_items=(),
        )
        response = BudgetedLLMProvider(self.session, self.provider).complete(
            task_id=task_id,
            context_package=context,
            request=LLMRequest(prompt_summary=goal, input_text=goal),
            max_total_tokens=8192,
            reserved_output_tokens=512,
            safety_margin_tokens=128,
        )
        llm_call = LLMCall(
            iteration_id=iteration.id,
            provider_name=response.provider,
            model_name=response.model,
            request_summary=goal,
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
        self.session.add(llm_call)
        self.session.flush()

        parsed = AgentActionParser(self.project_root).parse(json.loads(response.content))
        if parsed.outcome is ParseOutcome.REJECTED or parsed.action is None:
            llm_call.parse_status = ParseStatus.INVALID
            iteration.result = TaskIterationResult.ERROR
            self.session.flush()
            return IterationResult(iteration.id, None, None, True)

        action = self._record_action(task_id, iteration.id, llm_call.id, parsed.action)
        decision = GovernanceDecisionService(self.session).evaluate(
            task_id=task_id,
            action_id=action.id,
            proposal_hash=proposal_hash,
            revision=revision,
            rules=(),
            changed_paths=_changed_paths(parsed.action),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        if decision.decision != GovernanceVerdict.ALLOW:
            action.status = (
                AgentActionStatus.WAITING_APPROVAL
                if decision.decision == GovernanceVerdict.WARN
                else AgentActionStatus.BLOCKED
            )
            iteration.result = TaskIterationResult.NO_PROGRESS
            self.session.flush()
            return IterationResult(iteration.id, action.id, None, True)

        action.status = AgentActionStatus.EXECUTING
        tool_name = str(parsed.action.action_type)
        handler = self.tool_handlers[tool_name]
        tool_result = ToolDispatcher(self.session, self.registry).dispatch(
            task_id=task_id,
            action_id=action.id,
            tool_name=tool_name,
            parameters=parsed.action.model_dump(mode="json"),
            enforcer=lambda: True,
            handler=lambda: handler(parsed.action),
        )
        action.status = (
            AgentActionStatus.SUCCEEDED
            if tool_result.error_code is None
            else AgentActionStatus.FAILED
        )
        iteration.context_token_count = estimate_tokens(context.render())
        iteration.result = TaskIterationResult.PROGRESS
        self.session.flush()
        return IterationResult(iteration.id, action.id, tool_result, False)

    def _create_iteration(self, task_id: str) -> TaskIteration:
        next_number = (
            self.session.scalar(
                select(func.max(TaskIteration.iteration_number)).where(
                    TaskIteration.task_id == task_id
                )
            )
            or 0
        ) + 1
        iteration = TaskIteration(
            task_id=task_id,
            iteration_number=next_number,
            phase=TaskIterationPhase.EXECUTE,
        )
        self.session.add(iteration)
        self.session.flush()
        return iteration

    def _record_action(
        self,
        task_id: str,
        iteration_id: str,
        llm_call_id: str,
        parsed_action: Any,
    ) -> AgentAction:
        action = AgentAction(
            task_id=task_id,
            iteration_id=iteration_id,
            llm_call_id=llm_call_id,
            action_sequence=1,
            action_type=str(parsed_action.action_type),
            parameters_summary=json.dumps(parsed_action.model_dump(mode="json"), sort_keys=True),
            schema_version="v1",
            parse_status=ParseStatus.VALID,
            risk_level=RiskLevel.LOW,
            status=AgentActionStatus.GOVERNING,
            idempotency_key=f"{iteration_id}:1",
        )
        self.session.add(action)
        self.session.flush()
        return action


def _changed_paths(action: Any) -> tuple[str, ...]:
    path = getattr(action, "path", None)
    return (str(path),) if path else ()
