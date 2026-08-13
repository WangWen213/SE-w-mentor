from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph
from sqlalchemy.orm import Session

from se_mentor.approvals.decision_service import ApprovalDecisionService
from se_mentor.approvals.request_service import ApprovalRequestService
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.models.approval import (
    ApprovalDecisionOutcome,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import (
    GovernanceRuleEffect,
    GovernanceRuleScope,
    GovernanceVerdict,
)
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.dispatcher import ToolDispatcher
from se_mentor.tools.registry import ToolRegistry, ToolSpec


def test_E2E_03_warn_approval_scope(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    target = repo / "public_api.py"
    before_hash = _sha(target)
    engine = create_schema(tmp_path / "e2e03.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    calls: list[str] = []

    with session_scope(session_factory) as session:
        decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(_warn_public_api(),),
            changed_paths=("public_api.py",),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        request = ApprovalRequestService(session).create_for_decision(
            decision.id,
            requested_scope=("public_api.py",),
        )
        assert request is not None
        blocked = ToolDispatcher(session, _registry()).dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="APPLY_PATCH",
            parameters={"path": "public_api.py"},
            enforcer=lambda: False,
            handler=lambda: calls.append("before-approval"),
        )
        ApprovalDecisionService(session).record(
            task_id=ids["task_id"],
            request_id=request.id,
            approver_id="reviewer",
            outcome=ApprovalDecisionOutcome.APPROVED,
            approved_scope=("public_api.py",),
        )
        policy = _policy(session, ids, decision.id, request.id, ("public_api.py",))
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("public_api.py",),
            commands=(),
        )
        allowed = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=grant,
            relative_path="public_api.py",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("after-approval"),
        )
        outside = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=grant,
            relative_path="private_api.py",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("outside-scope"),
        )

    assert blocked.error_code == "POLICY_DENIED"
    assert _sha(target) == before_hash
    assert request.status == ApprovalRequestStatus.APPROVED
    assert allowed.allowed is True
    assert outside.allowed is False
    assert calls == ["after-approval"]


def test_E2E_04_deny_hard(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    before_hashes = _tree_hash(repo)
    engine = create_schema(tmp_path / "e2e04.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    calls: list[str] = []

    with session_scope(session_factory) as session:
        decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(_deny_recursive_delete(),),
            changed_paths=("scripts/remove-all.ps1",),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        request = ApprovalRequestService(session).create_for_decision(
            decision.id,
            requested_scope=("scripts/remove-all.ps1",),
        )
        blocked = ToolDispatcher(session, _registry()).dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="DELETE_FILE",
            parameters={"path": "scripts/remove-all.ps1"},
            enforcer=lambda: False,
            handler=lambda: calls.append("danger"),
        )

    assert decision.decision == GovernanceVerdict.BLOCK
    assert request is None
    assert blocked.error_code == "POLICY_DENIED"
    assert calls == []
    assert _tree_hash(repo) == before_hashes


def _copy_fixture(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "fixtures" / "e2e" / "governance"
    repo = tmp_path / "repo"
    shutil.copytree(source, repo)
    return repo


def _warn_public_api() -> RuleDefinition:
    return RuleDefinition(
        key="public-api-warn",
        name="Public API approval",
        scope=GovernanceRuleScope.SYSTEM,
        effect=GovernanceRuleEffect.REQUIRE_APPROVAL,
        priority=100,
        patterns=("public_api.py",),
        conditions={},
        reason="public API requires approval",
        overridable=True,
    )


def _deny_recursive_delete() -> RuleDefinition:
    return RuleDefinition(
        key="recursive-delete-deny",
        name="Recursive delete denied",
        scope=GovernanceRuleScope.SYSTEM,
        effect=GovernanceRuleEffect.DENY_HARD,
        priority=100,
        patterns=("scripts/remove-all.ps1",),
        conditions={},
        reason="recursive delete denied",
        overridable=False,
    )


def _policy(
    session: Session,
    ids: dict[str, str],
    decision_id: str,
    approval_request_id: str,
    write_paths: tuple[str, ...],
) -> ExecutionPolicy:
    policy = ExecutionPolicy(
        task_id=ids["task_id"],
        action_id=ids["action_id"],
        governance_decision_id=decision_id,
        approval_request_id=approval_request_id,
        proposal_hash=PROPOSAL_HASH,
        revision=REVISION,
        status=ExecutionPolicyStatus.ACTIVE,
        executable=True,
        read_paths_json=json.dumps(write_paths),
        write_paths_json=json.dumps(write_paths),
        protected_paths_json="[]",
        commands_json="[]",
        network_json='{"enabled":false}',
        resource_limits_json='{"timeout_seconds":30}',
        invalidation_json="{}",
        evidence_json='[{"source":"e2e"}]',
    )
    session.add(policy)
    session.flush()
    return policy


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec("APPLY_PATCH", "MEDIUM", 30))
    registry.register(ToolSpec("DELETE_FILE", "CRITICAL", 30))
    return registry


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): _sha(path)
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }
