from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
)


class ProposalGenerationError(ValueError):
    pass


class ProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    expected_behavior: str
    scope: list[str] = Field(min_length=1)
    non_goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(min_length=1)
    user_facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ProposalGenerator:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def generate(self, *, task_id: str, request: LLMRequest) -> ChangeProposal:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ProposalGenerationError("task not found")
        response = self.provider.complete(request)
        try:
            draft = ProposalDraft.model_validate_json(response.content)
        except ValidationError as exc:
            raise ProposalGenerationError("invalid proposal JSON") from exc
        version = self._next_version(task_id)
        proposal = ChangeProposal(
            task_id=task_id,
            version=version,
            goal=draft.goal,
            current_problem=json.dumps({"user_facts": draft.user_facts}, sort_keys=True),
            expected_behavior=draft.expected_behavior,
            initial_scope_json=json.dumps(draft.scope, sort_keys=True),
            excluded_scope_json=json.dumps(draft.non_goals, sort_keys=True),
            constraints_json=json.dumps(draft.constraints, sort_keys=True),
            assumptions_json=json.dumps({"user_facts": draft.user_facts}, sort_keys=True),
            risks_json=json.dumps(
                {"inferences": draft.inferences, "risks": draft.risks},
                sort_keys=True,
            ),
            acceptance_criteria_json=json.dumps(draft.acceptance, sort_keys=True),
            validation_plan_json=None,
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        self.session.add(proposal)
        self.session.flush()
        return proposal

    def _next_version(self, task_id: str) -> int:
        latest = self.session.scalars(
            select(ChangeProposal.version)
            .where(ChangeProposal.task_id == task_id)
            .order_by(ChangeProposal.version.desc())
        ).first()
        return int(latest or 0) + 1
