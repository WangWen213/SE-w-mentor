from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.approvals.decision_service import ApprovalDecisionService
from se_mentor.approvals.request_service import ApprovalRequestService
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import (
    ApprovalDecisionOutcome,
    ApprovalRequest,
    ApprovalRequestStatus,
)


def test_T048_fake_expired_or_cross_task_approval_is_rejected(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "approval-decision.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        request = ApprovalRequestService(session).create_for_decision(
            ids["decision_id"],
            requested_scope=("backend/src/app/api.py",),
        )
        assert request is not None
        service = ApprovalDecisionService(session)
        with pytest.raises(ValueError, match="cross_task"):
            service.record(
                task_id="other-task",
                request_id=request.id,
                approver_id="approver-1",
                outcome=ApprovalDecisionOutcome.APPROVED,
                approved_scope=("backend/src/app/api.py",),
            )
        request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        request.status = ApprovalRequestStatus.EXPIRED
        with pytest.raises(ValueError, match="expired"):
            service.record(
                task_id=ids["task_id"],
                request_id=request.id,
                approver_id="approver-1",
                outcome=ApprovalDecisionOutcome.APPROVED,
                approved_scope=("backend/src/app/api.py",),
            )
        request.expires_at = None
        request.status = ApprovalRequestStatus.PENDING
        decision = service.record(
            task_id=ids["task_id"],
            request_id=request.id,
            approver_id="approver-1",
            outcome=ApprovalDecisionOutcome.APPROVED,
            approved_scope=("backend/src/app/api.py",),
        )
        stored = session.get(ApprovalRequest, request.id)

    assert decision.decision_sequence == 1
    assert decision.approver_id == "approver-1"
    assert stored is not None
    assert stored.status == ApprovalRequestStatus.APPROVED
    assert "backend/src/app/api.py" in decision.evidence_json
