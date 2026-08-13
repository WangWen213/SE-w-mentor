from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.validation import ValidationPlan
from se_mentor.validation.planner import ImpactValidationInput, ValidationPlanner


def test_T070_api_schema_change_generates_contract_migration_and_unit_checks(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "planner.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["backend/src"]',
            write_paths_json='["backend/src"]',
            protected_paths_json='[".env"]',
            commands_json='["pytest","alembic"]',
            network_json='{"enabled": false}',
            resource_limits_json='{"timeout_seconds": 120}',
            invalidation_json='{"proposal_hash": true}',
            evidence_json='[{"source":"T070","summary":"policy"}]',
        )
        session.add(policy)
        session.flush()
        plan = ValidationPlanner(session).plan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy.id,
            revision=REVISION,
            impact=ImpactValidationInput(
                changed_paths=("backend/src/api/users.py", "backend/migrations/versions/next.py"),
                toolchain_frameworks=("pytest",),
            ),
        )
        stored = session.get(ValidationPlan, plan.id)

    assert stored is not None
    checks = json.loads(stored.required_checks_json)
    assert "contract" in checks
    assert "migration-empty-db" in checks
    assert "migration-existing-db" in checks
    assert "unit" in checks
    evidence = json.loads(stored.evidence_json)
    assert evidence["revision"] == REVISION
    assert evidence["inconclusive_preconditions"] == []
