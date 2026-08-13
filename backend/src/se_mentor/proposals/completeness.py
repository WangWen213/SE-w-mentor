from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from se_mentor.models.task import ChangeProposal, ProposalCompleteness, TaskStatus


class CompletenessDecision(StrEnum):
    COMPLETE = "COMPLETE"
    NEEDS_MORE_TECHNICAL_ANALYSIS = "NEEDS_MORE_TECHNICAL_ANALYSIS"
    NEEDS_USER_CLARIFICATION = "NEEDS_USER_CLARIFICATION"


@dataclass(frozen=True)
class CompletenessResult:
    decision: CompletenessDecision
    can_enter_analysis: bool
    missing: tuple[str, ...]
    technical_unknowns: tuple[str, ...] = ()
    user_decisions: tuple[str, ...] = ()


class ProposalCompletenessService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(self, proposal_id: str) -> CompletenessResult:
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        signals = _proposal_signals(proposal)
        missing = tuple(signals["missing"])
        technical_unknowns = tuple(signals["technical_unknowns"])
        user_decisions = tuple(signals["user_decisions"])
        if missing or technical_unknowns:
            proposal.completeness = ProposalCompleteness.INCOMPLETE
            task = proposal.task
            task.status = TaskStatus.DECIDING
            task.failure_code = "NEEDS_MORE_TECHNICAL_ANALYSIS"
            task.failure_message = _message(
                "Proposal needs more Mentor technical analysis",
                missing,
                technical_unknowns,
            )
            self.session.flush()
            return CompletenessResult(
                CompletenessDecision.NEEDS_MORE_TECHNICAL_ANALYSIS,
                False,
                missing,
                technical_unknowns,
                user_decisions,
            )
        if user_decisions:
            proposal.completeness = ProposalCompleteness.PARTIALLY_COMPLETE
            task = proposal.task
            task.status = TaskStatus.NEEDS_INFORMATION
            task.failure_code = "NEEDS_USER_CLARIFICATION"
            task.failure_message = "User decision required: " + "; ".join(user_decisions)
            self.session.flush()
            return CompletenessResult(
                CompletenessDecision.NEEDS_USER_CLARIFICATION,
                False,
                (),
                (),
                user_decisions,
            )
        proposal.completeness = ProposalCompleteness.COMPLETE
        task = proposal.task
        task.status = TaskStatus.PROPOSAL_REVIEW
        task.failure_code = None
        task.failure_message = None
        self.session.flush()
        return CompletenessResult(CompletenessDecision.COMPLETE, True, ())


def _proposal_signals(proposal: ChangeProposal) -> dict[str, list[str]]:
    missing: list[str] = []
    technical_unknowns: list[str] = []
    user_decisions: list[str] = []
    if not proposal.goal.strip():
        missing.append("goal")
    if not proposal.expected_behavior.strip():
        missing.append("expected_behavior")
    scope = _valid_json_list(proposal.initial_scope_json)
    acceptance = _valid_json_list(proposal.acceptance_criteria_json)
    validation = _valid_json_list(proposal.validation_plan_json)
    constraints = _valid_json_object(proposal.constraints_json)
    risks = _valid_json_object(proposal.risks_json)
    current_problem = _valid_json_object(proposal.current_problem)
    changes = constraints.get("changes")
    steps = constraints.get("steps")
    risk_items = risks.get("risks")
    constraints_list = constraints.get("constraints")
    if not scope:
        missing.append("scope")
    if not acceptance:
        missing.append("acceptance")
    if not validation:
        missing.append("validation")
    if not isinstance(changes, list) or not changes:
        missing.append("changes")
    if not isinstance(steps, list) or not steps:
        missing.append("steps")
    if not isinstance(risk_items, list) or not risk_items:
        missing.append("risks")
    if not _has_substantive_text(current_problem.get("understanding")):
        missing.append("understanding")
    for label, values in (
        ("scope", scope),
        ("changes", changes if isinstance(changes, list) else []),
        ("steps", steps if isinstance(steps, list) else []),
        ("validation", validation),
        ("risks", risk_items if isinstance(risk_items, list) else []),
        ("constraints", constraints_list if isinstance(constraints_list, list) else []),
    ):
        for value in values:
            text = _flatten(value)
            if _is_placeholder(text):
                technical_unknowns.append(f"{label}: {text}")
    user_decisions.extend(_user_decisions_from(proposal))
    return {
        "missing": _dedupe(missing),
        "technical_unknowns": _dedupe(technical_unknowns),
        "user_decisions": _dedupe(user_decisions),
    }


def _user_decisions_from(proposal: ChangeProposal) -> list[str]:
    assumptions = _valid_json_object(proposal.assumptions_json)
    decisions = assumptions.get("user_decisions")
    if isinstance(decisions, list):
        return [str(item) for item in decisions if str(item).strip()]
    missing_question = assumptions.get("missing_information_question")
    if isinstance(missing_question, str) and missing_question.strip():
        return [missing_question.strip()]
    return []


def _non_empty_json_list(value: str) -> bool:
    return bool(_valid_json_list(value))


def _valid_json_list(value: str | None) -> list[object]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _valid_json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _flatten(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values())
    return str(value)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    placeholders = ("unknown", "tbd", "todo", "n/a", "待补充", "暂未确定", "不确定", "待分析")
    return any(item in normalized for item in placeholders)


def _has_substantive_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(value.strip()) and not _is_placeholder(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _message(prefix: str, missing: tuple[str, ...], technical_unknowns: tuple[str, ...]) -> str:
    parts = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if technical_unknowns:
        parts.append("technical unknowns: " + "; ".join(technical_unknowns))
    return prefix + (" (" + " | ".join(parts) + ")" if parts else "")
