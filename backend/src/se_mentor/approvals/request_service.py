from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.approval import ApprovalRequest, ApprovalRequestStatus
from se_mentor.models.governance import GovernanceDecision, GovernanceVerdict


class ApprovalRequestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_for_decision(
        self,
        decision_id: str,
        *,
        requested_scope: tuple[str, ...],
    ) -> ApprovalRequest | None:
        decision = self.session.get(GovernanceDecision, decision_id)
        if decision is None:
            raise ValueError("governance decision not found")
        if decision.decision == GovernanceVerdict.BLOCK or not decision.approval_required:
            return None
        existing = self.session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.governance_decision_id == decision.id,
                ApprovalRequest.action_id == decision.action_id,
                ApprovalRequest.proposal_hash == decision.proposal_hash,
                ApprovalRequest.decision_revision == decision.revision,
                ApprovalRequest.status.in_(
                    [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.APPROVED]
                ),
            )
        )
        if existing is not None:
            return existing
        if decision.action_id is None:
            raise ValueError("approval request requires an action-bound decision")
        scope = tuple(sorted(requested_scope))
        request = ApprovalRequest(
            task_id=decision.task_id,
            action_id=decision.action_id,
            governance_decision_id=decision.id,
            decision_revision=decision.revision,
            proposal_hash=decision.proposal_hash,
            requested_scope_json=json.dumps(scope),
            status=ApprovalRequestStatus.PENDING,
            evidence_json=json.dumps(
                {
                    "governance_decision_id": decision.id,
                    "requested_scope": scope,
                    "reason": decision.reason_summary,
                },
                sort_keys=True,
            ),
        )
        self.session.add(request)
        self.session.flush()
        return request
