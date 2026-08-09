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
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus


@dataclass(frozen=True)
class ReGovernanceResult:
    task_id: str
    reason: str
    evidence_ref: str
    invalidated_policy_ids: tuple[str, ...]


class ReGovernanceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def trigger_new_scope(
        self,
        *,
        task_id: str,
        new_paths: tuple[str, ...],
        evidence_ref: str,
    ) -> ReGovernanceResult:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        for report in self.session.scalars(
            select(ImpactReport).where(
                ImpactReport.task_id == task_id,
                ImpactReport.status == ImpactReportStatus.CURRENT,
            )
        ):
            report.status = ImpactReportStatus.STALE
        for decision in self.session.scalars(
            select(GovernanceDecision).where(
                GovernanceDecision.task_id == task_id,
                GovernanceDecision.status == GovernanceDecisionStatus.ACTIVE,
            )
        ):
            decision.status = GovernanceDecisionStatus.SUPERSEDED
        for request in self.session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.task_id == task_id,
                ApprovalRequest.status.in_(
                    [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.APPROVED]
                ),
            )
        ):
            request.status = ApprovalRequestStatus.SUPERSEDED
        invalidated_policy_ids: list[str] = []
        for policy in self.session.scalars(
            select(ExecutionPolicy).where(
                ExecutionPolicy.task_id == task_id,
                ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE,
            )
        ):
            policy.status = ExecutionPolicyStatus.SUPERSEDED
            policy.executable = False
            invalidated_policy_ids.append(policy.id)
        for plan in self.session.scalars(
            select(ValidationPlan).where(
                ValidationPlan.task_id == task_id,
                ValidationPlan.status == ValidationPlanStatus.ACTIVE,
            )
        ):
            plan.status = ValidationPlanStatus.SUPERSEDED

        task.status = TaskStatus.BLOCKED
        task.failure_code = "ANALYSIS_REQUIRED"
        task.failure_message = (
            "New scope requires re-governance: "
            + ", ".join(sorted(new_paths))
            + f" ({evidence_ref})"
        )
        self.session.flush()
        return ReGovernanceResult(
            task_id=task_id,
            reason="new_file_scope",
            evidence_ref=evidence_ref,
            invalidated_policy_ids=tuple(sorted(invalidated_policy_ids)),
        )
