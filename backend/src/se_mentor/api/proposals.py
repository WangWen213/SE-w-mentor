from __future__ import annotations

import json
import logging
from time import perf_counter

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from se_mentor.api.envelope import error, ok
from se_mentor.api.projects import get_project_bootstrap_state, is_project_context_ready
from se_mentor.api.runtime import get_domain_provider, get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.llm.base import LLMRequest, ProviderError
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus, TaskStatus
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.proposals.context import ProposalContextBuilder
from se_mentor.proposals.generator import ProposalGenerationError, ProposalGenerator
from se_mentor.proposals.review_service import ProposalReviewService
from se_mentor.api.workbench_presentation import workbench_message_text

router = APIRouter(prefix="/api/tasks/{task_id}/proposals", tags=["proposals"])
_SESSION_FACTORY = get_session_factory()
LOGGER = logging.getLogger("se_mentor.api.proposals")


class ProposalCreate(BaseModel):
    goal: str
    missing_information_question: str | None = Field(
        default=None,
        alias="missingInformationQuestion",
    )


class ProposalAdjust(BaseModel):
    instruction: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_proposal(task_id: str, payload: ProposalCreate, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        if not is_project_context_ready(task.project_id):
            bootstrap_state = get_project_bootstrap_state(task.project_id)
            response.status_code = status.HTTP_409_CONFLICT
            message = (
                "Project analysis failed; proposal context is not available."
                if bootstrap_state.get("status") == "BOOTSTRAP_FAILED"
                else "Project analysis is not ready; proposal context is not available yet."
            )
            return error("CONTEXT_BUILD_FAILED", message)
        bootstrap_state = {"status": "READY"}
        if bootstrap_state.get("status") in {"REGISTERED", "BOOTSTRAPPING"}:
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", "Project analysis is not ready; proposal context is not available yet.")
        if bootstrap_state.get("status") == "BOOTSTRAP_FAILED":
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", "Project analysis is not ready; proposal context is not available yet.")
        try:
            context_started = perf_counter()
            context = ProposalContextBuilder(session).build_for_task(task_id, payload.goal.strip())
            LOGGER.info(
                "proposal.context_ms=%s task_id=%s context_chars=%s context_items=%s",
                int((perf_counter() - context_started) * 1000),
                task_id,
                context.context_package.char_count,
                len(context.context_package.items),
            )
        except Exception as exc:
            LOGGER.exception("PROPOSAL_CONTEXT failed task_id=%s", task_id)
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", _safe_message(exc, "Unable to build proposal context"))
        try:
            proposal = ProposalGenerator(session, get_domain_provider()).generate(
                task_id=task_id,
                request=LLMRequest(
                    prompt_summary="structured change proposal",
                    input_text=payload.goal.strip(),
                ),
                context_package=context.context_package,
                evidenced_paths=context.evidenced_paths,
            )
        except ProviderError as exc:
            _add_workbench_message(
                session,
                task_id=task_id,
                role="MENTOR",
                kind="ERROR",
                status="ERROR",
                text=f"方案生成失败：{_provider_message(exc)}",
            )
            response.status_code = status.HTTP_409_CONFLICT
            return error(_provider_error_code(exc), _provider_message(exc))
        except ProposalGenerationError as exc:
            _add_workbench_message(
                session,
                task_id=task_id,
                role="MENTOR",
                kind="ERROR",
                status="ERROR",
                text=f"方案生成失败：{exc}",
            )
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            return _proposal_generation_error(exc)
        except Exception as exc:
            LOGGER.exception("PROPOSAL_PERSIST failed task_id=%s", task_id)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("PROPOSAL_PERSIST_FAILED", _safe_message(exc, "Proposal persistence failed"))
        proposal_payload = _proposal_payload(proposal)
        _add_workbench_message(
            session,
            task_id=task_id,
            role="MENTOR",
            kind="PROPOSAL",
            status="DONE",
            text=_proposal_message_text(proposal),
            proposal_id=proposal.id,
        )
    return ok(proposal_payload)


@router.get("")
def current_proposal(task_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        proposal = None
        if task.active_proposal_id:
            active = session.get(ChangeProposal, task.active_proposal_id)
            if active is not None and active.task_id == task_id and active.status != ProposalStatus.SUPERSEDED:
                proposal = active
        if proposal is None:
            proposal = session.scalars(
                select(ChangeProposal)
                .where(ChangeProposal.task_id == task_id)
                .where(ChangeProposal.status != ProposalStatus.SUPERSEDED)
                .order_by(ChangeProposal.version.desc())
            ).first()
        if proposal is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        return ok(_proposal_payload(proposal))


@router.get("/history")
def proposal_history(task_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        proposals = session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.task_id == task_id)
            .order_by(ChangeProposal.version.asc())
        ).all()
        return ok(
            {
                "taskId": task_id,
                "items": [_proposal_payload(proposal) for proposal in proposals],
            }
        )


@router.post("/{proposal_id}/confirm")
def confirm_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        proposal = session.get(ChangeProposal, proposal_id)
        if proposal is None or proposal.task_id != task_id:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        try:
            ProposalReviewService(session).confirm_new_version(proposal_id, actor_id="webui-user")
        except ValueError as exc:
            response.status_code = status.HTTP_409_CONFLICT
            return error("PROPOSAL_CONFIRM_FAILED", str(exc))
        except Exception as exc:
            LOGGER.exception("PROPOSAL_CONFIRM failed task_id=%s proposal_id=%s", task_id, proposal_id)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("PROPOSAL_CONFIRM_FAILED", _safe_message(exc, "Proposal confirmation failed"))
        session.refresh(proposal)
        proposal_payload = _proposal_payload(proposal)
    return ok(proposal_payload)


@router.post("/{proposal_id}/reject")
def reject_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        proposal = session.get(ChangeProposal, proposal_id)
        if proposal is None or proposal.task_id != task_id:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        proposal.status = ProposalStatus.REJECTED
        task = session.get(ChangeTask, task_id)
        if task is not None:
            task.status = "CANCELLED"
        session.flush()
        proposal_payload = _proposal_payload(proposal)
    return ok(proposal_payload)


@router.post("/{proposal_id}/adjust", status_code=status.HTTP_201_CREATED)
def adjust_proposal(
    task_id: str,
    proposal_id: str,
    payload: ProposalAdjust,
    response: Response,
) -> dict[str, object]:
    instruction = payload.instruction.strip()
    if not instruction:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROPOSAL_ADJUSTMENT_REQUIRED", "proposal adjustment is required")
    with session_scope(_SESSION_FACTORY) as session:
        previous = session.get(ChangeProposal, proposal_id)
        if previous is None or previous.task_id != task_id:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        _add_workbench_message(
            session,
            task_id=task_id,
            role="USER",
            kind="TEXT",
            status="DONE",
            text=instruction,
        )
        if not is_project_context_ready(task.project_id):
            bootstrap_state = get_project_bootstrap_state(task.project_id)
            response.status_code = status.HTTP_409_CONFLICT
            message = (
                "Project analysis failed; proposal context is not available."
                if bootstrap_state.get("status") == "BOOTSTRAP_FAILED"
                else "Project analysis is not ready; proposal context is not available yet."
            )
            return error("CONTEXT_BUILD_FAILED", message)
        bootstrap_state = {"status": "READY"}
        if bootstrap_state.get("status") in {"REGISTERED", "BOOTSTRAPPING"}:
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", "Project analysis is not ready; proposal context is not available yet.")
        if bootstrap_state.get("status") == "BOOTSTRAP_FAILED":
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", "Project analysis is not ready; proposal context is not available yet.")
        try:
            context_started = perf_counter()
            context = ProposalContextBuilder(session).build_for_revision(
                task_id=task_id,
                follow_up=instruction,
                current_proposal=previous,
            )
            LOGGER.info(
                "proposal.context_ms=%s task_id=%s context_chars=%s context_items=%s",
                int((perf_counter() - context_started) * 1000),
                task_id,
                context.context_package.char_count,
                len(context.context_package.items),
            )
        except Exception as exc:
            LOGGER.exception("PROPOSAL_CONTEXT adjust failed task_id=%s", task_id)
            response.status_code = status.HTTP_409_CONFLICT
            return error("CONTEXT_BUILD_FAILED", _safe_message(exc, "Unable to build proposal context"))
        try:
            adjusted = ProposalGenerator(session, get_domain_provider()).generate(
                task_id=task_id,
                request=LLMRequest(
                    prompt_summary="structured adjusted change proposal",
                    input_text=_revision_input(task, previous, instruction),
                ),
                context_package=context.context_package,
                evidenced_paths=context.evidenced_paths,
            )
        except ProviderError as exc:
            _add_workbench_message(
                session,
                task_id=task_id,
                role="MENTOR",
                kind="ERROR",
                status="ERROR",
                text=f"方案调整失败：{_provider_message(exc)}",
            )
            response.status_code = status.HTTP_409_CONFLICT
            return error(_provider_error_code(exc), _provider_message(exc))
        except ProposalGenerationError as exc:
            _add_workbench_message(
                session,
                task_id=task_id,
                role="MENTOR",
                kind="ERROR",
                status="ERROR",
                text=f"方案调整失败：{exc}",
            )
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            return _proposal_generation_error(exc)
        except Exception as exc:
            LOGGER.exception("PROPOSAL_PERSIST adjust failed task_id=%s", task_id)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("PROPOSAL_PERSIST_FAILED", _safe_message(exc, "Proposal persistence failed"))
        previous.status = ProposalStatus.SUPERSEDED
        adjusted.supersedes_id = previous.id
        task = session.get(ChangeTask, task_id)
        if task is not None:
            task.active_proposal_id = None
            task.status = "CREATED"
        ProposalReviewService(session).invalidate_downstream_state(task_id, [previous.id])
        session.flush()
        proposal_payload = _proposal_payload(adjusted)
        _add_workbench_message(
            session,
            task_id=task_id,
            role="MENTOR",
            kind="PROPOSAL",
            status="DONE",
            text=_proposal_message_text(adjusted),
            proposal_id=adjusted.id,
        )
    return ok(proposal_payload)


def _proposal_message_text(proposal: ChangeProposal) -> str:
    if proposal.completeness == "COMPLETE":
        return f"我准备按这个完整范围处理：Proposal v{proposal.version}"
    if proposal.completeness == "PARTIALLY_COMPLETE":
        return f"Proposal v{proposal.version} 需要你补充一个产品决策后才能确认范围。"
    return f"Proposal v{proposal.version} 还需要 Mentor 补全技术分析，暂不能确认范围。"


def _proposal_payload(proposal: ChangeProposal) -> dict[str, object]:
    scope = _json_list(proposal.initial_scope_json)
    non_goals = _json_list(proposal.excluded_scope_json)
    current_problem = _json_object(proposal.current_problem)
    constraints = _json_object(proposal.constraints_json)
    assumptions = _json_object(proposal.assumptions_json)
    risks = _json_object(proposal.risks_json)
    acceptance = _json_list(proposal.acceptance_criteria_json)
    validation = _json_list(proposal.validation_plan_json)
    changes = _json_list_of_objects(constraints.get("changes"))
    steps = _json_string_list(constraints.get("steps"))
    constraints_list = _json_string_list(constraints.get("constraints"))
    understanding = str(current_problem.get("understanding") or proposal.goal)
    completeness = _proposal_completeness_payload(proposal, constraints, assumptions)
    display = _proposal_display_payload(
        proposal=proposal,
        understanding=understanding,
        scope=scope,
        non_goals=non_goals,
        changes=changes,
        steps=steps,
        acceptance=acceptance,
        validation=validation,
        risks=risks,
        completeness=completeness,
    )
    return {
        "id": proposal.id,
        "taskId": proposal.task_id,
        "version": proposal.version,
        "goal": proposal.goal,
        "understanding": understanding,
        "target": proposal.goal,
        "currentProblem": proposal.current_problem,
        "expectedBehavior": proposal.expected_behavior,
        "scope": scope,
        "changes": changes,
        "steps": steps,
        "constraints": constraints_list,
        "nonGoals": non_goals,
        "assumptions": assumptions,
        "risks": risks,
        "acceptanceCriteria": acceptance,
        "validation": validation,
        "executionBoundary": scope,
        "items": scope,
        "impact": f"{len(scope)} 个范围项待分析",
        "risk": ", ".join(str(item) for item in risks.get("risks", [])) or "待治理分析",
        "missingInformationQuestion": _missing_information_question(completeness),
        "completeness": completeness,
        "display": display,
        "status": proposal.status,
        "supersedesId": proposal.supersedes_id,
    }


def _proposal_completeness_payload(
    proposal: ChangeProposal,
    constraints: dict[str, object],
    assumptions: dict[str, object],
) -> dict[str, object]:
    technical_unknowns = _proposal_technical_unknowns(proposal, constraints)
    user_decisions = _json_string_list(assumptions.get("user_decisions"))
    if proposal.completeness == "COMPLETE":
        decision = "COMPLETE"
        can_confirm = True
    elif user_decisions and not technical_unknowns:
        decision = "NEEDS_USER_CLARIFICATION"
        can_confirm = False
    else:
        decision = "NEEDS_MORE_TECHNICAL_ANALYSIS"
        can_confirm = False
    return {
        "decision": decision,
        "canConfirm": can_confirm,
        "technicalUnknowns": technical_unknowns,
        "userDecisions": user_decisions,
    }


def _proposal_technical_unknowns(proposal: ChangeProposal, constraints: dict[str, object]) -> list[str]:
    values = [
        proposal.goal,
        proposal.expected_behavior,
        proposal.initial_scope_json,
        proposal.acceptance_criteria_json,
        proposal.validation_plan_json,
        json.dumps(constraints, ensure_ascii=False, sort_keys=True),
    ]
    unknowns: list[str] = []
    for value in values:
        lowered = str(value).lower()
        if any(marker in lowered for marker in ("unknown", "tbd", "todo", "待补充", "待分析", "暂未确定", "不确定")):
            unknowns.append(str(value)[:180])
    return list(dict.fromkeys(unknowns))


def _missing_information_question(completeness: dict[str, object]) -> str | None:
    if completeness["decision"] != "NEEDS_USER_CLARIFICATION":
        return None
    decisions = completeness.get("userDecisions")
    if isinstance(decisions, list) and decisions:
        return str(decisions[0])
    return None


def _proposal_display_payload(
    *,
    proposal: ChangeProposal,
    understanding: str,
    scope: list[str],
    non_goals: list[str],
    changes: list[dict[str, object]],
    steps: list[str],
    acceptance: list[str],
    validation: list[str],
    risks: dict[str, object],
    completeness: dict[str, object],
) -> dict[str, object]:
    user_decisions = _json_string_list(completeness.get("userDecisions"))
    technical_unknowns = _json_string_list(completeness.get("technicalUnknowns"))
    return {
        "title": proposal.goal,
        "understanding": understanding,
        "goal": proposal.expected_behavior,
        "preparedChanges": [
            {
                "path": str(change.get("path") or "候选实现位置，执行阶段进一步定位"),
                "symbol": change.get("symbol"),
                "action": str(change.get("action") or "补充实现细节"),
                "reason": str(change.get("reason") or "属于本轮修改范围"),
            }
            for change in changes
        ],
        "scope": scope,
        "nonGoals": non_goals,
        "steps": steps,
        "expectedImpact": _expected_impact(scope, changes),
        "risks": _json_string_list(risks.get("risks")),
        "validation": [*validation, *acceptance],
        "needsUserDecision": user_decisions or ["暂无需要你决定的问题。"],
        "technicalUnknowns": technical_unknowns,
    }


def _expected_impact(scope: list[str], changes: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    for change in changes:
        path = str(change.get("path") or "").strip()
        reason = str(change.get("reason") or "").strip()
        if path:
            values.append(f"{path}: {reason or '本轮可能影响的实现位置'}")
    if not values:
        values = [f"{item}: 本轮范围内需要关注的影响面" for item in scope]
    return values


def _revision_input(task: ChangeTask, previous: ChangeProposal, instruction: str) -> str:
    return "\n".join(
        [
            f"Original user request: {task.original_request}",
            "Current proposal JSON:",
            json.dumps(_proposal_payload(previous), ensure_ascii=False, sort_keys=True),
            f"Follow-up instruction: {instruction}",
        ]
    )


def _proposal_generation_error(exc: ProposalGenerationError) -> dict[str, object]:
    return error(
        exc.code,
        str(exc),
        actualKeys=exc.actual_keys,
        expectedKeys=exc.expected_keys,
        validationErrors=exc.validation_errors,
    )


def _add_workbench_message(
    session,
    *,
    task_id: str,
    role: str,
    kind: str,
    status: str,
    text: str,
    proposal_id: str | None = None,
) -> None:
    sequence = int(
        session.scalar(
            select(func.coalesce(func.max(WorkbenchMessage.sequence), 0))
            .where(WorkbenchMessage.task_id == task_id)
        )
        or 0
    ) + 1
    session.add(
        WorkbenchMessage(
            task_id=task_id,
            sequence=sequence,
            role=role,
            kind=kind,
            status=status,
            text=workbench_message_text(role=role, kind=kind, text=text),
            proposal_id=proposal_id,
        )
    )


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    data = json.loads(value)
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    data = json.loads(value)
    if isinstance(data, dict):
        return data
    return {}


def _json_list_of_objects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _json_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _provider_error_code(exc: ProviderError) -> str:
    if str(exc) == "PROVIDER_UNAVAILABLE":
        return "PROVIDER_UNAVAILABLE"
    return exc.code


def _provider_message(exc: ProviderError) -> str:
    code = _provider_error_code(exc)
    if str(exc) == "PROVIDER_UNAVAILABLE":
        return "LLM provider is not configured. Configure credentials in Settings and regenerate the proposal."
    if code == "PROVIDER_CONFIG_INVALID":
        return "LLM provider configuration is incomplete. Check Provider, Base URL, and Model."
    if code == "PROVIDER_REQUEST_BUILD_FAILED":
        return f"LLM provider request could not be built: {_provider_detail(exc)}"
    if code in {"PROVIDER_HTTP_401", "PROVIDER_HTTP_403"}:
        return f"LLM provider authentication failed ({code.removeprefix('PROVIDER_')}): {_provider_detail(exc)}"
    if code == "PROVIDER_HTTP_429":
        return f"LLM provider rate limit ({code.removeprefix('PROVIDER_')}): {_provider_detail(exc)}"
    if code.startswith("PROVIDER_HTTP_"):
        return f"LLM provider request failed ({code.removeprefix('PROVIDER_')}): {_provider_detail(exc)}"
    if code == "PROVIDER_CONNECTION_ERROR":
        return f"LLM provider connection failed: {_provider_detail(exc)}"
    if code == "PROVIDER_REQUEST_FAILED":
        return f"LLM provider request failed: {_provider_detail(exc)}"
    if code == "PROVIDER_TIMEOUT":
        return "LLM provider timed out. The task was created, but the proposal could not be generated."
    if code == "PROVIDER_INVALID_RESPONSE":
        return f"LLM provider returned an invalid response: {_provider_detail(exc)}"
    return str(exc)


def _safe_message(exc: Exception, fallback: str) -> str:
    message = str(exc).strip()
    return message or fallback


def _provider_detail(exc: ProviderError) -> str:
    return _safe_message(exc, "no provider detail available")


def _mark_governance_failed(session, task_id: str, exc: Exception) -> None:
    task = session.get(ChangeTask, task_id)
    if task is None:
        return
    task.status = TaskStatus.FAILED
    task.failure_code = "GOVERNANCE_FAILED"
    task.failure_message = _safe_message(exc, "Governance failed")
