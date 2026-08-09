from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.approval import (
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.task import ChangeProposal, ProposalStatus, TaskStatus
from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus


@dataclass(frozen=True)
class ProposalReviewResult:
    confirmed_proposal_id: str
    superseded_proposal_ids: tuple[str, ...]


class ProposalReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def can_write_execution(self, proposal_id: str) -> bool:
        proposal = self.session.get(ChangeProposal, proposal_id)
        return proposal is not None and proposal.status == ProposalStatus.CONFIRMED

    def confirm_new_version(self, proposal_id: str, *, actor_id: str) -> ProposalReviewResult:
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        if proposal.completeness != "COMPLETE":
            raise ValueError("proposal must be complete before confirmation")

        superseded_ids = self._supersede_other_proposals(proposal)
        proposal.status = ProposalStatus.CONFIRMED
        task = proposal.task
        task.active_proposal_id = proposal.id
        task.status = TaskStatus.GOVERNING
        task.failure_code = None
        task.failure_message = f"Proposal confirmed by {actor_id}"

        self._invalidate_downstream_state(proposal.task_id, superseded_ids)
        self.session.flush()
        return ProposalReviewResult(proposal.id, tuple(superseded_ids))

    def _supersede_other_proposals(self, proposal: ChangeProposal) -> list[str]:
        superseded_ids: list[str] = []
        proposals = self.session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.task_id == proposal.task_id)
            .where(ChangeProposal.id != proposal.id)
            .where(ChangeProposal.status != ProposalStatus.SUPERSEDED)
            .order_by(ChangeProposal.version)
        ).all()
        for older in proposals:
            older.status = ProposalStatus.SUPERSEDED
            superseded_ids.append(older.id)
        return superseded_ids

    def _invalidate_downstream_state(self, task_id: str, old_proposal_ids: list[str]) -> None:
        if old_proposal_ids:
            for report in self.session.scalars(
                select(ImpactReport).where(ImpactReport.proposal_id.in_(old_proposal_ids))
            ):
                report.status = ImpactReportStatus.SUPERSEDED
            for plan in self.session.scalars(
                select(ValidationPlan).where(ValidationPlan.proposal_id.in_(old_proposal_ids))
            ):
                plan.status = ValidationPlanStatus.SUPERSEDED

        for decision in self.session.scalars(
            select(GovernanceDecision)
            .where(GovernanceDecision.task_id == task_id)
            .where(GovernanceDecision.status == GovernanceDecisionStatus.ACTIVE)
        ):
            decision.status = GovernanceDecisionStatus.SUPERSEDED

        for request in self.session.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.task_id == task_id)
            .where(
                ApprovalRequest.status.in_(
                    [
                        ApprovalRequestStatus.PENDING,
                        ApprovalRequestStatus.APPROVED,
                    ]
                )
            )
        ):
            request.status = ApprovalRequestStatus.SUPERSEDED

        for policy in self.session.scalars(
            select(ExecutionPolicy)
            .where(ExecutionPolicy.task_id == task_id)
            .where(ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE)
        ):
            policy.status = ExecutionPolicyStatus.SUPERSEDED
            policy.executable = False
