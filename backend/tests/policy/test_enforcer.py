from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import TemporaryGrantService


def test_T051_dispatcher_cannot_execute_outside_policy_even_if_orchestrator_marks_allowed(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "policy-enforcer.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    calls: list[str] = []

    with session_scope(session_factory) as session:
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=None,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["backend/src/app/api.py"]',
            write_paths_json='["backend/src/app/api.py"]',
            protected_paths_json='[".env"]',
            commands_json='["pytest"]',
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":30}',
            invalidation_json='{"proposal_hash":"aaaaaaaa"}',
            evidence_json='[{"source":"test"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("backend/src/app/api.py",),
            commands=("pytest",),
        )
        result = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=grant,
            relative_path="../outside.py",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("called"),
        )

    assert result.allowed is False
    assert result.reason == "outside_policy"
    assert calls == []
