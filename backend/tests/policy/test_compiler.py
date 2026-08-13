from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicyStatus
from se_mentor.policy.compiler import ExecutionPolicyCompiler


def test_T049_warn_without_approval_produces_no_write_grant(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "policy-compiler.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        policy = ExecutionPolicyCompiler(session).compile(
            governance_decision_id=ids["decision_id"],
            read_paths=("backend/src/app/api.py",),
            write_paths=("backend/src/app/api.py",),
            commands=("pytest",),
            protected_paths=(".env",),
            network={"enabled": False},
            resource_limits={"timeout_seconds": 30},
        )

    assert policy.proposal_hash == PROPOSAL_HASH
    assert policy.revision == REVISION
    assert policy.status == ExecutionPolicyStatus.ACTIVE
    assert policy.executable is False
    assert json.loads(policy.read_paths_json) == ["backend/src/app/api.py"]
    assert json.loads(policy.write_paths_json) == []
    assert json.loads(policy.commands_json) == []
    assert json.loads(policy.protected_paths_json) == [".env"]
    assert "approval_required" in policy.invalidation_json
