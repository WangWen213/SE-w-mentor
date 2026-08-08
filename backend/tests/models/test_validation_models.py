from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, execute, seed_task_graph
from sqlalchemy import Engine, exc

from se_mentor.contracts.enums import EventType, FeedbackKind, FeedbackSeverity
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.validation import (
    FeedbackSignal,
    ProgressEvent,
    ValidationPlan,
    ValidationPlanStatus,
    ValidationRun,
    ValidationRunStatus,
    ValidationType,
)


def test_T015_passed_validation_requires_zero_exit_and_no_required_failure(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "validation.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    policy_id = _insert_policy(engine, ids)

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO validation_runs (
                id, validation_plan_id, run_order, validation_type, command_summary,
                exit_code, status, required, required_failure, log_artifact_ref, created_at
            )
            VALUES (
                'bad-passed', :plan_id, 1, 'TEST', 'pytest', 1, 'PASSED',
                1, 0, 'artifact://logs/bad.log', CURRENT_TIMESTAMP
            )
            """,
            {"plan_id": _insert_plan(engine, ids, policy_id)},
        )

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO validation_runs (
                id, validation_plan_id, run_order, validation_type, command_summary,
                exit_code, status, required, required_failure, log_artifact_ref, created_at
            )
            VALUES (
                'bad-required', :plan_id, 2, 'TEST', 'pytest', 0, 'PASSED',
                1, 1, 'artifact://logs/bad.log', CURRENT_TIMESTAMP
            )
            """,
            {"plan_id": _insert_plan(engine, ids, policy_id, version=2)},
        )


def test_T015_plan_version_run_order_and_shared_feedback_enums(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "validation-ok.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    policy_id = _insert_policy(engine, ids)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        plan = ValidationPlan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy_id,
            version=1,
            status=ValidationPlanStatus.ACTIVE,
            required_checks_json='["pytest"]',
            evidence_json='[{"source":"T015","summary":"plan"}]',
        )
        session.add(plan)
        session.flush()
        session.add(
            ValidationRun(
                validation_plan_id=plan.id,
                run_order=1,
                validation_type=ValidationType.TEST,
                command_summary="pytest",
                exit_code=0,
                status=ValidationRunStatus.PASSED,
                required=True,
                required_failure=False,
                log_artifact_ref="artifact://logs/pytest.log",
            )
        )
        session.add(
            FeedbackSignal(
                task_id=ids["task_id"],
                kind=FeedbackKind.VALIDATION,
                severity=FeedbackSeverity.INFO,
                summary="Validation passed.",
                evidence_json='[{"source":"T015","summary":"feedback"}]',
            )
        )
        session.add(
            ProgressEvent(
                task_id=ids["task_id"],
                event_type=EventType.VALIDATION_RECORDED,
                summary="Validation recorded.",
                evidence_json='[{"source":"T015","summary":"progress"}]',
            )
        )
        session.flush()

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO validation_runs (
                id, validation_plan_id, run_order, validation_type, command_summary,
                exit_code, status, required, required_failure, log_artifact_ref, created_at
            )
            SELECT 'duplicate-order', id, 1, 'TEST', 'pytest', 0, 'PASSED',
                   1, 0, 'artifact://logs/dup.log', CURRENT_TIMESTAMP
            FROM validation_plans LIMIT 1
            """,
            {},
        )


def _insert_policy(engine: Engine, ids: dict[str, str]) -> str:
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
            commands_json='["pytest"]',
            network_json='{"enabled": false}',
            resource_limits_json='{"timeout_seconds": 120}',
            invalidation_json='{"proposal_hash": true}',
            evidence_json='[{"source":"T015","summary":"policy"}]',
        )
        session.add(policy)
        session.flush()
        return policy.id


def _insert_plan(engine: Engine, ids: dict[str, str], policy_id: str, *, version: int = 1) -> str:
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        plan = ValidationPlan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy_id,
            version=version,
            status=ValidationPlanStatus.ACTIVE,
            required_checks_json='["pytest"]',
            evidence_json='[{"source":"T015","summary":"plan"}]',
        )
        session.add(plan)
        session.flush()
        return plan.id
