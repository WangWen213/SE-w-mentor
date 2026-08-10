from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.validation import ValidationPlan, ValidationRun, ValidationRunStatus
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.registry import ToolRegistry, ToolSpec
from se_mentor.validation.executor import CommandResult, ValidationExecutor


def test_T071_required_nonzero_exit_makes_plan_failed_and_records_artifact(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "executor.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    log_root = tmp_path / "validation-logs"

    with session_scope(session_factory) as session:
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["."]',
            write_paths_json='["."]',
            protected_paths_json='[".env"]',
            commands_json='["pytest"]',
            network_json='{"enabled": false}',
            resource_limits_json='{"timeout_seconds": 120}',
            invalidation_json='{"proposal_hash": true}',
            evidence_json='[{"source":"T071","summary":"policy"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=(".",),
            commands=("pytest",),
        )
        plan = ValidationPlan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy.id,
            version=1,
            status="ACTIVE",
            required_checks_json=json.dumps(["unit"]),
            evidence_json='{"revision":"phase1-revision"}',
        )
        session.add(plan)
        session.flush()
        registry = ToolRegistry()
        registry.register(ToolSpec("RUN_VALIDATION", "validation", 120))
        result = ValidationExecutor(
            session,
            registry=registry,
            log_root=log_root,
            runner=lambda command: CommandResult(1, "1 failed", "", 7),
        ).execute(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            plan_id=plan.id,
            policy_id=policy.id,
            grant=grant,
            revision=REVISION,
        )
        run = session.query(ValidationRun).one()

    assert result.passed is False
    assert run.status == ValidationRunStatus.FAILED
    assert run.exit_code == 1
    assert run.required_failure is True
    assert Path(run.log_artifact_ref).read_text(encoding="utf-8") == "STDOUT:\n1 failed\nSTDERR:\n"
    assert result.dispatch_status == "OK"
    assert result.policy_checked is True
