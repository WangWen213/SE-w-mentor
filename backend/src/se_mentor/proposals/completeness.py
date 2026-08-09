from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from se_mentor.models.task import ChangeProposal, ProposalCompleteness, TaskStatus


class CompletenessDecision(StrEnum):
    COMPLETE = "COMPLETE"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"


@dataclass(frozen=True)
class CompletenessResult:
    decision: CompletenessDecision
    can_enter_analysis: bool
    missing: tuple[str, ...]


class ProposalCompletenessService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(self, proposal_id: str) -> CompletenessResult:
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        missing = tuple(_missing_fields(proposal))
        if missing:
            proposal.completeness = ProposalCompleteness.INCOMPLETE
            proposal.status = proposal.status
            task = proposal.task
            task.status = TaskStatus.BLOCKED
            task.failure_code = "NEEDS_INFORMATION"
            task.failure_message = "Missing proposal fields: " + ", ".join(missing)
            self.session.flush()
            return CompletenessResult(CompletenessDecision.NEEDS_INFORMATION, False, missing)
        proposal.completeness = ProposalCompleteness.COMPLETE
        self.session.flush()
        return CompletenessResult(CompletenessDecision.COMPLETE, True, ())


def _missing_fields(proposal: ChangeProposal) -> list[str]:
    missing: list[str] = []
    if not proposal.goal.strip():
        missing.append("goal")
    if not proposal.expected_behavior.strip():
        missing.append("expected_behavior")
    if not _non_empty_json_list(proposal.initial_scope_json):
        missing.append("scope")
    if not _non_empty_json_list(proposal.acceptance_criteria_json):
        missing.append("acceptance")
    return missing


def _non_empty_json_list(value: str) -> bool:
    return bool(_valid_json_list(value))


def _valid_json_list(value: str) -> list[object]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
