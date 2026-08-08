from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, execute, seed_task_graph
from sqlalchemy import exc

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import (
    ApprovalDecision,
    ApprovalDecisionOutcome,
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import GovernanceVerdict


def test_T013_approval_for_old_proposal_cannot_attach_to_new_policy(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "approval.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        request = ApprovalRequest(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            decision_revision=REVISION,
            proposal_hash=PROPOSAL_HASH,
            requested_scope_json='["backend/src"]',
            status=ApprovalRequestStatus.PENDING,
            evidence_json='[{"source":"T013","summary":"request"}]',
        )
        session.add(request)
        session.flush()
        request_id = request.id

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO execution_policies (
                id, task_id, action_id, governance_decision_id, approval_request_id,
                proposal_hash, revision, status, executable, read_paths_json,
                write_paths_json, protected_paths_json, commands_json, network_json,
                resource_limits_json, invalidation_json, evidence_json, created_at
            )
            VALUES (
                'bad-old-approval', :task_id, :action_id, :decision_id, :request_id,
                :new_hash, :revision, 'ACTIVE', 1, '[]', '[]', '[]', '[]', '{}',
                '{}', '{}', '[]', CURRENT_TIMESTAMP
            )
            """,
            {
                "task_id": ids["task_id"],
                "action_id": ids["action_id"],
                "decision_id": ids["decision_id"],
                "request_id": request_id,
                "new_hash": "c" * 64,
                "revision": REVISION,
            },
        )


def test_T013_approval_history_and_block_policy_constraints(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "approval-history.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        request = ApprovalRequest(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            decision_revision=REVISION,
            proposal_hash=PROPOSAL_HASH,
            requested_scope_json='["backend/src"]',
            status=ApprovalRequestStatus.PENDING,
            evidence_json='[{"source":"T013","summary":"request"}]',
        )
        session.add(request)
        session.flush()
        session.add_all(
            [
                ApprovalDecision(
                    approval_request_id=request.id,
                    decision_sequence=1,
                    outcome=ApprovalDecisionOutcome.APPROVED,
                    approver_id="user-1",
                    approved_scope_json='["backend/src"]',
                    evidence_json='[{"source":"user","summary":"approved"}]',
                ),
                ApprovalDecision(
                    approval_request_id=request.id,
                    decision_sequence=2,
                    outcome=ApprovalDecisionOutcome.REVOKED,
                    approver_id="user-1",
                    approved_scope_json="[]",
                    evidence_json='[{"source":"user","summary":"revoked"}]',
                ),
            ]
        )
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=request.id,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["backend/src"]',
            write_paths_json='["backend/src/se_mentor/models"]',
            protected_paths_json='[".env"]',
            commands_json='["pytest"]',
            network_json='{"enabled": false}',
            resource_limits_json='{"timeout_seconds": 120}',
            invalidation_json='{"proposal_hash": true}',
            evidence_json='[{"source":"T013","summary":"policy"}]',
        )
        session.add(policy)
        session.flush()

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO execution_policies (
                id, task_id, action_id, governance_decision_id, proposal_hash, revision,
                status, executable, read_paths_json, write_paths_json, protected_paths_json,
                commands_json, network_json, resource_limits_json, invalidation_json,
                evidence_json, created_at
            )
            VALUES (
                'bad-block-policy', :task_id, :action_id, :blocked_decision_id,
                :proposal_hash, :revision, 'ACTIVE', 1, '[]', '[]', '[]',
                '[]', '{}', '{}', '{}', '[]', CURRENT_TIMESTAMP
            )
            """,
            {
                "task_id": ids["task_id"],
                "action_id": ids["action_id"],
                "blocked_decision_id": ids["blocked_decision_id"],
                "proposal_hash": "b" * 64,
                "revision": REVISION,
            },
        )

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO approval_decisions (
                id, approval_request_id, decision_sequence, outcome, approver_id,
                approved_scope_json, evidence_json, created_at
            )
            VALUES (
                'bad-outcome', 'missing', 0, 'MAYBE', '', '', '', CURRENT_TIMESTAMP
            )
            """,
            {},
        )

    assert GovernanceVerdict.BLOCK == "BLOCK"
