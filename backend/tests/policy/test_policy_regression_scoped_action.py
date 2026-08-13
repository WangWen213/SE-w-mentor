from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph
from sqlalchemy import select

from se_mentor.contracts.enums import ToolStatus
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.execution.orchestrator import _current_authorization
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import (
    FileChange,
    ToolExecution,
    ToolExecutionStatus,
    WorkspaceLockMode,
)
from se_mentor.models.governance import GovernanceVerdict
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.policy.compiler import ExecutionPolicyCompiler
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import ExecutionAuthorization
from se_mentor.tools.apply_patch import AtomicApplyPatchTool, StructuredPatch
from se_mentor.tools.dispatcher import ToolDispatcher
from se_mentor.tools.registry import ToolRegistry, ToolSpec
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_action_bound_allow_reconstructs_policy_for_scoped_write_after_resume(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "policy-regression.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    requested_path = "frontend/src/app/fixtures.ts"
    calls: list[str] = []

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.ACTION_PENDING
        decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(),
            changed_paths=(requested_path,),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        policy = ExecutionPolicyCompiler(session).compile(
            governance_decision_id=decision.id,
            read_paths=(requested_path,),
            write_paths=(requested_path,),
            commands=("RUN_COMMAND",),
            protected_paths=(),
            network={},
            resource_limits={},
        )
        task.active_policy_id = policy.id

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        policy = session.get(ExecutionPolicy, task.active_policy_id)
        assert policy is not None
        authorization = ExecutionAuthorization.from_policy(policy)
        allowed = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=authorization,
            relative_path=requested_path,
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("write"),
        )
        outside = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=authorization,
            relative_path="../outside.txt",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("outside"),
        )
        unapproved = PolicyEnforcer(session).dispatch_write(
            policy_id=policy.id,
            grant=authorization,
            relative_path="frontend/src/app/AppShell.tsx",
            revision=REVISION,
            orchestrator_allowed=True,
            handler=lambda: calls.append("unapproved"),
        )

    assert json.loads(policy.write_paths_json) == [requested_path]
    assert policy.status == ExecutionPolicyStatus.ACTIVE
    assert allowed.allowed is True
    assert allowed.reason == "allowed"
    assert outside.allowed is False
    assert outside.reason == "outside_policy"
    assert unapproved.allowed is False
    assert unapproved.reason == "outside_policy"
    assert calls == ["write"]


def test_action_bound_policy_dispatches_real_patch_and_records_file_change(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    target = repo / "frontend" / "src" / "app" / "fixtures.ts"
    target.parent.mkdir(parents=True)
    target.write_text(
        'export const nav = [{ key: "tasks", label: "任务9", marker: "T" }];\n',
        encoding="utf-8",
    )
    before_hash = _sha(target)

    engine = create_schema(tmp_path / "policy-dispatch.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    requested_path = "frontend/src/app/fixtures.ts"
    stale_path = "frontend/src/app/AppShell.tsx"
    registry = ToolRegistry()
    registry.register(ToolSpec("APPLY_PATCH", "write", 30))

    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="policy-regression-test",
        reason="verify action-bound scoped write",
    )
    assert lock.lock is not None

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.ACTION_PENDING
        stale_decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(),
            changed_paths=(stale_path,),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        stale_policy = ExecutionPolicyCompiler(session).compile(
            governance_decision_id=stale_decision.id,
            read_paths=(stale_path,),
            write_paths=(stale_path,),
            commands=("RUN_COMMAND",),
            protected_paths=(),
            network={},
            resource_limits={},
        )
        action_decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(),
            changed_paths=(requested_path,),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        action_policy = ExecutionPolicyCompiler(session).compile(
            governance_decision_id=action_decision.id,
            read_paths=(requested_path,),
            write_paths=(requested_path,),
            commands=("RUN_COMMAND",),
            protected_paths=(),
            network={},
            resource_limits={},
        )
        task.active_policy_id = action_policy.id
        fallback_grant = ExecutionAuthorization.from_policy(stale_policy)
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
        )
        enforcement_reason = "not_checked"

        def enforce_path(path: str) -> bool:
            nonlocal enforcement_reason
            grant = _current_authorization(session, task, fallback=fallback_grant)
            result = PolicyEnforcer(session).dispatch_write(
                policy_id=grant.policy_id,
                grant=grant,
                relative_path=path,
                revision=grant.revision,
                orchestrator_allowed=True,
                handler=lambda: None,
            )
            enforcement_reason = result.reason
            return result.allowed

        result = ToolDispatcher(session, registry).dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="APPLY_PATCH",
            parameters={"relative_path": requested_path},
            enforcer=lambda: enforce_path(requested_path),
            enforcement_reason=lambda: enforcement_reason,
            handler=lambda: AtomicApplyPatchTool(session, project_root=repo).apply(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=_current_authorization(session, task, fallback=fallback_grant),
                patch=StructuredPatch(
                    requested_path,
                    before_hash,
                    (('"tasks", label: "任务9"', '"tasks", label: "任务10"'),),
                ),
                revision=_current_authorization(session, task, fallback=fallback_grant).revision,
            ),
        )
        stale_policy_status = stale_policy.status
        action_policy_status = action_policy.status
        change = session.scalar(select(FileChange).where(FileChange.task_id == ids["task_id"]))
        execution = session.get(ToolExecution, result.tool_execution_id)

        denied = ToolDispatcher(session, registry).dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="APPLY_PATCH",
            parameters={"relative_path": stale_path},
            enforcer=lambda: enforce_path(stale_path),
            enforcement_reason=lambda: enforcement_reason,
            handler=lambda: "should not run",
        )
        denied_execution = session.get(ToolExecution, denied.tool_execution_id)

    assert stale_policy_status == ExecutionPolicyStatus.SUPERSEDED
    assert action_policy_status == ExecutionPolicyStatus.ACTIVE
    assert result.status == ToolStatus.OK
    assert execution is not None
    assert execution.status == ToolExecutionStatus.SUCCEEDED
    assert change is not None
    assert change.relative_path == requested_path
    assert change.tool_execution_id == result.tool_execution_id
    assert change.before_hash == before_hash
    assert change.after_hash == _sha(target)
    assert change.before_hash != change.after_hash
    assert 'label: "任务10"' in target.read_text(encoding="utf-8")
    assert denied.status == ToolStatus.BLOCKED
    assert denied.error_code == "POLICY_DENIED_WRITE_PATH"
    assert denied.summary == "policy denied: outside_policy"
    assert denied_execution is not None
    assert denied_execution.status == ToolExecutionStatus.BLOCKED
    assert json.loads(denied_execution.evidence_json)["result"]["policy_reason"] == "outside_policy"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
