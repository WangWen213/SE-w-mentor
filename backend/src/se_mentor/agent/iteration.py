from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from se_mentor.agent.action_parser import AgentActionParser, ParseOutcome
from se_mentor.context.context_builder import ContextBuilder, ContextItem, TrustLabel
from se_mentor.context.token_budget import BudgetedLLMProvider, estimate_tokens
from se_mentor.contracts.actions import AgentActionAdapter
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.governance import GovernanceDecision, GovernanceVerdict
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
from se_mentor.policy.compiler import ExecutionPolicyCompiler
from se_mentor.runtime.profiles import RuntimeProfile, get_runtime_settings
from se_mentor.tools.dispatcher import ToolDispatcher, ToolDispatchResult
from se_mentor.tools.registry import ToolRegistry

LOGGER = logging.getLogger("se_mentor.agent.iteration")
StagePublisher = Callable[[str, str, str | None], None]


@dataclass(frozen=True)
class IterationResult:
    iteration_id: str
    action_id: str | None
    tool_result: ToolDispatchResult | None
    paused: bool
    feedback: str | None = None
    feedback_artifact_ref: str | None = None


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
        enforcers: dict[str, Callable[[Any], bool]] | None = None,
        governance_rules: tuple[RuleDefinition, ...] = (),
    ) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()
        self.context_builder = context_builder
        self.provider = provider
        self.registry = registry
        self.tool_handlers = tool_handlers
        self.enforcers = enforcers or {}
        self.governance_rules = governance_rules

    def run(
        self,
        *,
        task_id: str,
        proposal_hash: str,
        revision: str,
        goal: str,
        feedback: str = "none",
        publish_stage: StagePublisher | None = None,
    ) -> IterationResult:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        total_started = perf_counter()
        context_started = perf_counter()
        iteration = self._create_iteration(task_id)
        context = self.context_builder.build(
            goal=goal,
            governance_items=(
                ContextItem(
                    "governance", "governance", "governance required", 100, TrustLabel.SYSTEM
                ),
                ContextItem(
                    "tool-catalog",
                    "tools",
                    _tool_catalog_text(self.registry),
                    100,
                    TrustLabel.SYSTEM,
                ),
            ),
            execution_policy=ContextItem(
                "policy",
                "policy",
                _execution_policy_text(goal, feedback),
                95,
                TrustLabel.SYSTEM,
            ),
            current_error=ContextItem("feedback", "feedback", feedback, 90, TrustLabel.TOOL_OUTPUT),
            repository_items=(),
            knowledge_items=(),
        )
        context_ms = int((perf_counter() - context_started) * 1000)
        LOGGER.info(
            (
                "[perf] execution.turn.context task_id=%s turn=%s duration_ms=%s "
                "context_chars=%s context_items=%s"
            ),
            task_id,
            iteration.iteration_number,
            context_ms,
            context.char_count,
            len(context.items),
        )
        _publish(publish_stage, "LLM_REQUESTED", "OK", f"iteration_id={iteration.id}")
        provider_started = perf_counter()
        response = BudgetedLLMProvider(self.session, self.provider).complete(
            task_id=task_id,
            context_package=context,
            request=LLMRequest(
                prompt_summary=goal,
                input_text=goal,
                response_schema=AgentActionAdapter.json_schema(),
            ),
            max_total_tokens=8192,
            reserved_output_tokens=512,
            safety_margin_tokens=128,
        )
        provider_ms = int((perf_counter() - provider_started) * 1000)
        LOGGER.info(
            (
                "[perf] execution.turn.provider task_id=%s turn=%s duration_ms=%s "
                "input_tokens=%s output_tokens=%s response_chars=%s"
            ),
            task_id,
            iteration.iteration_number,
            provider_ms,
            response.usage.input_tokens,
            response.usage.output_tokens,
            len(response.content),
        )
        _publish(publish_stage, "LLM_RESPONDED", "OK", f"iteration_id={iteration.id}")
        parse_started = perf_counter()
        parse_error: str | None = None
        parsed_payload: dict[str, Any] | None = None
        try:
            parsed_payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            parse_error = f"invalid agent action: malformed JSON at character {exc.pos}"
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

        if parsed_payload is None:
            parse_ms = int((perf_counter() - parse_started) * 1000)
            llm_call.parse_status = ParseStatus.INVALID
            iteration.result = TaskIterationResult.ERROR
            self.session.flush()
            persist_ms = int((perf_counter() - parse_started) * 1000) - parse_ms
            LOGGER.info(
                (
                    "[perf] execution.turn.persist task_id=%s turn=%s duration_ms=%s "
                    "result=parse_error"
                ),
                task_id,
                iteration.iteration_number,
                max(persist_ms, 0),
            )
            artifact_ref = self._write_parse_failure_artifact(
                task_id=task_id,
                iteration_id=iteration.id,
                llm_call_id=llm_call.id,
                response_content=response.content,
                parser_error=parse_error or "malformed JSON",
            )
            llm_call.response_summary = _parse_failure_summary(
                response.content, parse_error or "malformed JSON", artifact_ref
            )
            self.session.flush()
            LOGGER.info(
                (
                    "[perf] execution.turn.persist task_id=%s turn=%s duration_ms=0 "
                    "result=parse_rejected"
                ),
                task_id,
                iteration.iteration_number,
            )
            _log_iteration_perf(
                task_id=task_id,
                iteration_number=iteration.iteration_number,
                context_ms=context_ms,
                provider_ms=provider_ms,
                parse_ms=parse_ms,
                governance_ms=0,
                dispatch_ms=0,
                tool_ms=0,
                total_started=total_started,
            )
            return IterationResult(iteration.id, None, None, True, parse_error, artifact_ref)

        parsed = AgentActionParser(self.project_root).parse(parsed_payload)
        parse_ms = int((perf_counter() - parse_started) * 1000)
        if parsed.outcome is ParseOutcome.REJECTED or parsed.action is None:
            llm_call.parse_status = ParseStatus.INVALID
            iteration.result = TaskIterationResult.ERROR
            self.session.flush()
            feedback_message = (
                parsed.feedback.message if parsed.feedback is not None else "invalid agent action"
            )
            artifact_ref = self._write_parse_failure_artifact(
                task_id=task_id,
                iteration_id=iteration.id,
                llm_call_id=llm_call.id,
                response_content=response.content,
                parser_error=parsed.error_detail or feedback_message,
            )
            llm_call.response_summary = _parse_failure_summary(
                response.content, feedback_message, artifact_ref
            )
            self.session.flush()
            _log_iteration_perf(
                task_id=task_id,
                iteration_number=iteration.iteration_number,
                context_ms=context_ms,
                provider_ms=provider_ms,
                parse_ms=parse_ms,
                governance_ms=0,
                dispatch_ms=0,
                tool_ms=0,
                total_started=total_started,
            )
            return IterationResult(iteration.id, None, None, True, feedback_message, artifact_ref)

        action = self._record_action(task_id, iteration.id, llm_call.id, parsed.action)
        governance_started = perf_counter()
        decision = GovernanceDecisionService(self.session).evaluate(
            task_id=task_id,
            action_id=action.id,
            proposal_hash=proposal_hash,
            revision=revision,
            rules=self.governance_rules,
            changed_paths=_changed_paths(parsed.action),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        governance_ms = int((perf_counter() - governance_started) * 1000)
        if decision.decision != GovernanceVerdict.ALLOW:
            action.status = (
                AgentActionStatus.WAITING_APPROVAL
                if decision.decision == GovernanceVerdict.WARN
                else AgentActionStatus.BLOCKED
            )
            iteration.result = TaskIterationResult.NO_PROGRESS
            self.session.flush()
            _log_iteration_perf(
                task_id=task_id,
                iteration_number=iteration.iteration_number,
                context_ms=context_ms,
                provider_ms=provider_ms,
                parse_ms=parse_ms,
                governance_ms=governance_ms,
                dispatch_ms=0,
                tool_ms=0,
                total_started=total_started,
            )
            return IterationResult(
                iteration.id,
                action.id,
                None,
                True,
                f"governance decision {decision.decision}",
            )

        action.status = AgentActionStatus.EXECUTING
        self._activate_action_policy(decision.id, _changed_paths(parsed.action))
        tool_name = str(parsed.action.action_type)
        handler = self.tool_handlers[tool_name]
        enforcer = self.enforcers.get(tool_name, lambda _action: True)
        enforcement_reason = "not_checked"

        def enforce_action() -> bool:
            nonlocal enforcement_reason
            result = enforcer(parsed.action)
            if isinstance(result, tuple):
                allowed, reason = result
                enforcement_reason = str(reason)
                return bool(allowed)
            enforcement_reason = "allowed" if result else "policy_denied"
            return bool(result)

        _publish(publish_stage, "TOOL_DISPATCHED", "OK", f"action_id={action.id} tool={tool_name}")
        dispatch_started = perf_counter()
        tool_result = ToolDispatcher(self.session, self.registry).dispatch(
            task_id=task_id,
            action_id=action.id,
            tool_name=tool_name,
            parameters=parsed.action.model_dump(mode="json"),
            enforcer=enforce_action,
            enforcement_reason=lambda: enforcement_reason,
            handler=lambda: handler(parsed.action),
        )
        dispatch_ms = int((perf_counter() - dispatch_started) * 1000)
        LOGGER.info(
            ("[perf] execution.turn.tool task_id=%s turn=%s duration_ms=%s tool=%s error=%s"),
            task_id,
            iteration.iteration_number,
            dispatch_ms,
            tool_name,
            tool_result.error_code is not None,
        )
        persist_started = perf_counter()
        action.status = (
            AgentActionStatus.SUCCEEDED
            if tool_result.error_code is None
            else AgentActionStatus.FAILED
        )
        iteration.context_token_count = estimate_tokens(context.render())
        iteration.result = TaskIterationResult.PROGRESS
        self.session.flush()
        persist_ms = int((perf_counter() - persist_started) * 1000)
        LOGGER.info(
            ("[perf] execution.turn.persist task_id=%s turn=%s duration_ms=%s result=progress"),
            task_id,
            iteration.iteration_number,
            persist_ms,
        )
        LOGGER.info(
            (
                "[perf] execution.turn.total task_id=%s turn=%s duration_ms=%s "
                "context_ms=%s provider_ms=%s tool_ms=%s persist_ms=%s"
            ),
            task_id,
            iteration.iteration_number,
            int((perf_counter() - total_started) * 1000),
            context_ms,
            provider_ms,
            dispatch_ms,
            persist_ms,
        )
        _log_iteration_perf(
            task_id=task_id,
            iteration_number=iteration.iteration_number,
            context_ms=context_ms,
            provider_ms=provider_ms,
            parse_ms=parse_ms,
            governance_ms=governance_ms,
            dispatch_ms=dispatch_ms,
            tool_ms=dispatch_ms,
            total_started=total_started,
        )
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
        next_sequence = (
            self.session.scalar(
                select(func.max(AgentAction.action_sequence)).where(
                    AgentAction.iteration_id == iteration_id
                )
            )
            or 0
        ) + 1
        action = AgentAction(
            task_id=task_id,
            iteration_id=iteration_id,
            llm_call_id=llm_call_id,
            action_sequence=next_sequence,
            action_type=str(parsed_action.action_type),
            parameters_summary=json.dumps(parsed_action.model_dump(mode="json"), sort_keys=True),
            schema_version="v1",
            parse_status=ParseStatus.VALID,
            risk_level=RiskLevel.LOW,
            status=AgentActionStatus.GOVERNING,
            idempotency_key=f"{iteration_id}:{next_sequence}",
        )
        self.session.add(action)
        self.session.flush()
        return action

    def _activate_action_policy(
        self,
        governance_decision_id: str,
        changed_paths: tuple[str, ...],
    ) -> None:
        if not changed_paths:
            return
        decision = self.session.get(GovernanceDecision, governance_decision_id)
        if decision is None:
            return
        active = self.session.scalar(
            select(ExecutionPolicy).where(
                ExecutionPolicy.task_id == decision.task_id,
                ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE,
            )
        )
        if active is not None:
            return
        policy = ExecutionPolicyCompiler(self.session).compile(
            governance_decision_id=governance_decision_id,
            read_paths=changed_paths,
            write_paths=changed_paths,
            commands=_execution_commands(),
            protected_paths=(),
            network={},
            resource_limits={},
        )
        task = self.session.get(ChangeTask, policy.task_id)
        if task is not None:
            task.active_policy_id = policy.id
        self.session.flush()

    def _write_parse_failure_artifact(
        self,
        *,
        task_id: str,
        iteration_id: str,
        llm_call_id: str,
        response_content: str,
        parser_error: str,
    ) -> str:
        artifact_dir = self.project_root.parent / ".sementor" / "llm-parse-failures" / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{iteration_id}-{uuid4().hex}.json"
        payload = {
            "task_id": task_id,
            "iteration_id": iteration_id,
            "llm_call_id": llm_call_id,
            "parser_error": parser_error,
            "sanitized_response": _sanitize_provider_text(response_content),
        }
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
        )
        return str(artifact_path)


def _changed_paths(action: Any) -> tuple[str, ...]:
    parameters = getattr(action, "parameters", None)
    path = getattr(parameters, "path", None)
    if path:
        return (str(path),)
    patch_path = getattr(parameters, "relative_path", None)
    return (str(patch_path),) if patch_path else ()


def _tool_catalog_text(registry: ToolRegistry) -> str:
    registered = {spec.name for spec in registry.list_specs()}
    schema = AgentActionAdapter.json_schema()
    action_defs = schema.get("$defs", {}) if isinstance(schema, dict) else {}
    lines = [
        "Registered production AgentAction tools. Return exactly one schema-valid action.",
        "READ_FILE: read repository source context only. parameters: path, start_line, end_line.",
        (
            "SEARCH_CODE: locate repository evidence. parameters: query. "
            "Result includes match path, line, and excerpt."
        ),
        (
            "APPLY_PATCH: canonical tool for modifying an existing file. parameters: "
            "relative_path, optional expected_sha256, replacements[{old,new}]. "
            "Use it once enough evidence identifies the exact edit. Include optional "
            "target_evidence with selected_path, selected_excerpt, user_target_description, "
            "matched_semantic_evidence, alternative_candidates, and selection_reason when "
            "multiple literal matches exist."
        ),
        "CREATE_FILE: canonical write tool for adding a new file. parameters: path, content.",
        "DELETE_FILE: canonical write tool for deleting a file. parameters: path.",
        (
            "RUN_COMMAND: validation or read-only inspection command only. "
            "Do not use RUN_COMMAND for text replacement, file creation, deletion, "
            "sed/perl/python rewrite scripts, or any code modification."
        ),
        "Registered tool names: " + ", ".join(sorted(registered)),
        (
            'Schema-correct APPLY_PATCH example: {"action_type":"APPLY_PATCH",'
            '"parameters":{"relative_path":"frontend/src/example.tsx","expected_sha256":null,'
            '"replacements":[{"old":"old text","new":"new text"}],'
            '"target_evidence":{"selected_path":"frontend/src/example.tsx",'
            '"selected_excerpt":"old text","user_target_description":"requested UI location",'
            '"matched_semantic_evidence":["navigation"],"alternative_candidates":[],'
            '"selection_reason":"Selected path matches the requested UI role."}},'
            '"reason":"Apply the confirmed code change after reading the target file."}'
        ),
    ]
    if action_defs:
        available_defs = [name for name in sorted(action_defs) if name.endswith("Action")]
        lines.append("Canonical action schema definitions: " + ", ".join(available_defs))
    return "\n".join(lines)


def _execution_policy_text(goal: str, feedback: str) -> str:
    return "\n".join(
        [
            "You are executing an already confirmed coding change.",
            "requires_code_change=true",
            "A coding task is not complete until a real FileChange exists.",
            "Use READ_FILE or SEARCH_CODE only to gather evidence required for the edit.",
            (
                "Once sufficient evidence exists, perform an allowed WRITE action: "
                "APPLY_PATCH, CREATE_FILE, or DELETE_FILE."
            ),
            "Do not stop after investigation, and do not use RUN_COMMAND to perform source edits.",
            (
                "The execution goal below includes the original request, confirmed proposal, "
                "allowed write scope, and live progress counters."
            ),
            goal,
            "Current feedback:",
            feedback,
        ]
    )


def _execution_commands() -> tuple[str, ...]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return ("APPLY_APPROVED_CHANGES",)
    return ("RUN_COMMAND",)


def _sanitize_provider_text(text: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", text)
    redacted = re.sub(r"(?i)(authorization|api[-_ ]?key|bearer)\s*[:=]\s*\S+", r"\1: ***", redacted)
    return redacted[:8192]


def _parse_failure_summary(response_content: str, feedback_message: str, artifact_ref: str) -> str:
    summary = (
        f"{len(response_content)} chars; parser_error={feedback_message}; artifact={artifact_ref}"
    )
    return summary[:2048]


def _publish(
    publisher: StagePublisher | None, stage: str, status: str, detail: str | None = None
) -> None:
    if publisher is not None:
        publisher(stage, status, detail)


def _log_iteration_perf(
    *,
    task_id: str,
    iteration_number: int,
    context_ms: int,
    provider_ms: int,
    parse_ms: int,
    governance_ms: int,
    dispatch_ms: int,
    tool_ms: int,
    total_started: float,
) -> None:
    LOGGER.info(
        (
            "[perf] execution-iteration task_id=%s iteration=%s context_ms=%s "
            "provider_ms=%s parse_ms=%s governance_ms=%s dispatch_ms=%s "
            "tool_ms=%s feedback_ms=0 total_ms=%s"
        ),
        task_id,
        iteration_number,
        context_ms,
        provider_ms,
        parse_ms,
        governance_ms,
        dispatch_ms,
        tool_ms,
        int((perf_counter() - total_started) * 1000),
    )
