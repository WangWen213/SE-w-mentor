from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from se_mentor.models.approval import (
    ApprovalDecision,
    ApprovalDecisionOutcome,
    ApprovalRequest,
    ApprovalRequestStatus,
)
from se_mentor.models.governance import GovernanceVerdict


class ApprovalDecisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        task_id: str,
        request_id: str,
        approver_id: str,
        outcome: ApprovalDecisionOutcome,
        approved_scope: tuple[str, ...],
    ) -> ApprovalDecision:
        request = self.session.get(ApprovalRequest, request_id)
        if request is None:
            raise ValueError("approval request not found")
        if request.task_id != task_id:
            raise ValueError("cross_task approval request reuse rejected")
        if request.status == ApprovalRequestStatus.EXPIRED or _is_expired(request):
            raise ValueError("expired approval request rejected")
        if request.governance_decision.decision == GovernanceVerdict.BLOCK:
            raise ValueError("deny hard decision cannot be approved")

        sequence = self._next_sequence(request.id)
        scope = tuple(sorted(approved_scope))
        decision = ApprovalDecision(
            approval_request_id=request.id,
            decision_sequence=sequence,
            outcome=outcome,
            approver_id=approver_id,
            approved_scope_json=json.dumps(scope),
            evidence_json=json.dumps(
                {"approver_id": approver_id, "approved_scope": scope, "outcome": outcome},
                sort_keys=True,
                default=str,
            ),
        )
        request.status = _request_status(outcome)
        self.session.add(decision)
        self.session.flush()
        return decision

    def _next_sequence(self, request_id: str) -> int:
        current = self.session.scalar(
            select(func.max(ApprovalDecision.decision_sequence)).where(
                ApprovalDecision.approval_request_id == request_id
            )
        )
        return int(current or 0) + 1


def _is_expired(request: ApprovalRequest) -> bool:
    return request.expires_at is not None and request.expires_at <= datetime.now(UTC)


def _request_status(outcome: ApprovalDecisionOutcome) -> ApprovalRequestStatus:
    if outcome == ApprovalDecisionOutcome.APPROVED:
        return ApprovalRequestStatus.APPROVED
    if outcome == ApprovalDecisionOutcome.REJECTED:
        return ApprovalRequestStatus.REJECTED
    return ApprovalRequestStatus.EXPIRED
