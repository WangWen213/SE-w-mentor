from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.governance.regovernance import ReGovernanceService
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import TemporaryGrantService


def test_T052_new_file_scope_invalidates_policy_before_write(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "regovernance.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    calls: list[str] = []

    with session_scope(session_factory) as session:
        report = ImpactReport(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            base_revision=REVISION,
            direct_impacts_json='["backend/src/app/api.py"]',
            evidence_json='[{"source":"test"}]',
            status=ImpactReportStatus.CURRENT,
        )
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
        session.add_all([report, policy])
        session.flush()
        plan = ValidationPlan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy.id,
            version=1,
            status=ValidationPlanStatus.ACTIVE,
            required_checks_json='["pytest"]',
            evidence_json='[{"source":"test"}]',
        )
        session.add(plan)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("backend/src/app/api.py",),
            commands=("pytest",),
        )
        result = ReGovernanceService(session).trigger_new_scope(
            task_id=ids["task_id"],
            new_paths=("backend/src/app/new_module.py",),
            evidence_ref="diff://new-file",
        )
        enforcement = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=grant,
            relative_path="backend/src/app/api.py",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("called"),
        )
        task = session.get(ChangeTask, ids["task_id"])
        decision = session.get(GovernanceDecision, ids["decision_id"])

    assert result.reason == "new_file_scope"
    assert policy.status == ExecutionPolicyStatus.SUPERSEDED
    assert policy.executable is False
    assert report.status == ImpactReportStatus.STALE
    assert decision is not None
    assert decision.status == GovernanceDecisionStatus.SUPERSEDED
    assert plan.status == ValidationPlanStatus.SUPERSEDED
    assert task is not None
    assert task.status == TaskStatus.BLOCKED
    assert task.failure_code == "ANALYSIS_REQUIRED"
    assert enforcement.allowed is False
    assert enforcement.reason == "inactive_policy"
    assert calls == []
