from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph
from sqlalchemy.orm import Session

from se_mentor.agent.completion_gate import CompletionGate, CompletionSnapshot
from se_mentor.agent.repair_loop import RepairAttempt, RepairLoop
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.update_success import SuccessfulTaskResult, SuccessKnowledgeUpdater
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import WorkspaceLockMode
from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus
from se_mentor.policy.grants import TemporaryGrant, TemporaryGrantService
from se_mentor.tools.apply_patch import AtomicApplyPatchTool, StructuredPatch
from se_mentor.tools.registry import ToolRegistry, ToolSpec
from se_mentor.transactions.manager import TransactionManager
from se_mentor.validation.executor import (
    CommandResult,
    ValidationExecutionResult,
    ValidationExecutor,
)
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_E2E_01_normal_change_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _copy_fixture(tmp_path)
    _init_git(repo)
    network_calls: list[str] = []
    monkeypatch.setattr(
        socket, "create_connection", lambda *args, **kwargs: network_calls.append("net")
    )
    engine = create_schema(tmp_path / "e2e01.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="e2e",
        reason="normal change",
    )
    assert lock.lock is not None

    before = _sha(repo / "app.py")
    with session_scope(session_factory) as session:
        policy, grant, plan = _policy_and_plan(session, ids, ("app.py", "."))
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
        )
        applied = AtomicApplyPatchTool(session, project_root=repo).apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch(
                "app.py",
                before,
                (('return "old"', 'return "new"'),),
            ),
            revision=REVISION,
        )
        validation = _validate(session, tmp_path, ids, policy.id, grant, plan.id, should_pass=True)
        completion = CompletionGate().evaluate(
            CompletionSnapshot(
                True, True, validation.passed, False, False, False, True, True, False
            )
        )
        knowledge = SuccessKnowledgeUpdater(repo).extract(
            SuccessfulTaskResult(
                task_id=ids["task_id"],
                revision=REVISION,
                committed_diff=applied.diff,
                changed_paths=("app.py",),
                passed_validation_refs=("evidence/test-reports/T081.xml",),
                final_summary="updated app response",
            )
        )

    assert applied.before_sha256 != applied.after_sha256
    assert validation.passed is True
    assert validation.policy_checked is True
    assert completion.can_complete is True
    assert knowledge
    assert network_calls == []


def test_E2E_02_failed_then_repaired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _copy_fixture(tmp_path)
    _init_git(repo)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    engine = create_schema(tmp_path / "e2e02.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="e2e",
        reason="repair change",
    )
    assert lock.lock is not None

    with session_scope(session_factory) as session:
        policy, grant, plan = _policy_and_plan(session, ids, ("app.py", "."))
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
        )
        first_before = _sha(repo / "app.py")
        first = AtomicApplyPatchTool(session, project_root=repo).apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch("app.py", first_before, (('return "old"', 'return "broken"'),)),
            revision=REVISION,
        )
        first_validation = _validate(
            session, tmp_path, ids, policy.id, grant, plan.id, should_pass=False
        )
        loop = RepairLoop(session, max_repairs=3)
        first_decision = loop.record_attempt(
            task_id=ids["task_id"],
            attempt=RepairAttempt(first.after_sha256, "unit failed", False),
        )
        second = AtomicApplyPatchTool(session, project_root=repo).apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch(
                "app.py", first.after_sha256, (('return "broken"', 'return "new"'),)
            ),
            revision=REVISION,
        )
        repair_plan = _validation_plan(session, ids, policy.id, version=2)
        second_validation = _validate(
            session, tmp_path, ids, policy.id, grant, repair_plan.id, should_pass=True
        )
        second_decision = loop.record_attempt(
            task_id=ids["task_id"],
            attempt=RepairAttempt(second.after_sha256, "", True),
        )

    assert first_validation.passed is False
    assert second_validation.passed is True
    assert first.diff != second.diff
    assert first_decision.continue_repair is True
    assert second_decision.completed is True
    assert second_decision.distinct_diffs == 2


def _copy_fixture(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "fixtures" / "e2e" / "basic_fix"
    repo = tmp_path / "repo"
    shutil.copytree(source, repo)
    return repo


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "e2e@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "E2E"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _policy_and_plan(
    session: Session,
    ids: dict[str, str],
    write_paths: tuple[str, ...],
) -> tuple[ExecutionPolicy, TemporaryGrant, ValidationPlan]:
    policy = ExecutionPolicy(
        task_id=ids["task_id"],
        action_id=ids["action_id"],
        governance_decision_id=ids["decision_id"],
        approval_request_id=None,
        proposal_hash=PROPOSAL_HASH,
        revision=REVISION,
        status=ExecutionPolicyStatus.ACTIVE,
        executable=True,
        read_paths_json=json.dumps(sorted(write_paths)),
        write_paths_json=json.dumps(sorted(write_paths)),
        protected_paths_json="[]",
        commands_json='["pytest"]',
        network_json='{"enabled":false}',
        resource_limits_json='{"timeout_seconds":30}',
        invalidation_json="{}",
        evidence_json='[{"source":"e2e"}]',
    )
    session.add(policy)
    session.flush()
    plan = ValidationPlan(
        task_id=ids["task_id"],
        proposal_id=ids["proposal_id"],
        execution_policy_id=policy.id,
        version=1,
        status=ValidationPlanStatus.ACTIVE,
        required_checks_json='["unit"]',
        evidence_json='[{"source":"e2e"}]',
    )
    session.add(plan)
    session.flush()
    grant = TemporaryGrantService(session).create(
        policy.id,
        write_paths=write_paths,
        commands=("pytest",),
    )
    return policy, grant, plan


def _validation_plan(
    session: Session,
    ids: dict[str, str],
    policy_id: str,
    *,
    version: int,
) -> ValidationPlan:
    plan = ValidationPlan(
        task_id=ids["task_id"],
        proposal_id=ids["proposal_id"],
        execution_policy_id=policy_id,
        version=version,
        status=ValidationPlanStatus.ACTIVE,
        required_checks_json='["unit"]',
        evidence_json='[{"source":"e2e"}]',
    )
    session.add(plan)
    session.flush()
    return plan


def _validate(
    session: Session,
    tmp_path: Path,
    ids: dict[str, str],
    policy_id: str,
    grant: TemporaryGrant,
    plan_id: str,
    *,
    should_pass: bool,
) -> ValidationExecutionResult:
    registry = ToolRegistry()
    registry.register(ToolSpec("RUN_VALIDATION", "LOW", 30))
    return ValidationExecutor(
        session,
        registry=registry,
        log_root=tmp_path / "validation-logs",
        runner=lambda command: CommandResult(0 if should_pass else 1, "ok", "", 5),
    ).execute(
        task_id=ids["task_id"],
        action_id=ids["action_id"],
        plan_id=plan_id,
        policy_id=policy_id,
        grant=grant,
        revision=REVISION,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
