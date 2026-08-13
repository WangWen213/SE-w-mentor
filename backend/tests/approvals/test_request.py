from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.approvals.request_service import ApprovalRequestService
from se_mentor.db.session import create_session_factory, session_scope


def test_T047_block_creates_no_approval_and_warn_request_is_scope_bound(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "approval-request.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        service = ApprovalRequestService(session)
        blocked = service.create_for_decision(
            ids["blocked_decision_id"],
            requested_scope=("backend/src/app/api.py",),
        )
        request = service.create_for_decision(
            ids["decision_id"],
            requested_scope=("backend/src/app/api.py",),
        )
        same = service.create_for_decision(
            ids["decision_id"],
            requested_scope=("backend/src/app/api.py",),
        )

    assert blocked is None
    assert request is not None
    assert same is not None
    assert same.id == request.id
    assert request.task_id == ids["task_id"]
    assert request.action_id == ids["action_id"]
    assert request.proposal_hash == PROPOSAL_HASH
    assert request.decision_revision == REVISION
    assert json.loads(request.requested_scope_json) == ["backend/src/app/api.py"]
    assert "backend/src/app/api.py" in request.evidence_json
