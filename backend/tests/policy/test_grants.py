from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.policy.grants import TemporaryGrantService


def test_T050_grant_cannot_expand_scope_or_survive_revision_change(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "temporary-grant.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

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
        service = TemporaryGrantService(session)
        with pytest.raises(ValueError, match="expand_scope"):
            service.create(
                policy.id,
                write_paths=("backend/src/app/api.py", "backend/src/app/extra.py"),
                commands=("pytest",),
            )
        grant = service.create(
            policy.id,
            write_paths=("backend/src/app/api.py",),
            commands=("pytest",),
        )

    assert grant.task_id == ids["task_id"]
    assert grant.action_id == ids["action_id"]
    assert grant.allows_write("backend/src/app/api.py", revision=REVISION) is True
    assert grant.allows_write(".env", revision=REVISION) is False
    assert grant.allows_write("backend/src/app/api.py", revision="new-revision") is False
