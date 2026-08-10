from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import ToolExecution, WorkspaceLockMode
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.shell import ShellTool, ShellToolError
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_T062_shell_injection_env_secret_cwd_escape_and_timeout_are_blocked(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "shell.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="shell",
    )
    assert lock.lock is not None

    with session_scope(session_factory) as session:
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
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
            read_paths_json='["."]',
            write_paths_json='["."]',
            protected_paths_json='[".env"]',
            commands_json=json.dumps([sys.executable]),
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":1}',
            invalidation_json='{"proposal_hash":"aaaaaaaa"}',
            evidence_json='[{"source":"test"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=(".",),
            commands=(sys.executable,),
        )
        tool = ShellTool(
            session,
            project_root=repo,
            parent_env={**os.environ, "OPENAI_API_KEY": "sk-proj_abcdefghijklmnopqrstuvwxyz"},
        )
        with pytest.raises(ShellToolError, match="command injection"):
            tool.run(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                program="cmd",
                args=("/c", "echo injected"),
                cwd=".",
                revision=REVISION,
            )
        with pytest.raises(ShellToolError, match="cwd escape"):
            tool.run(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                program=sys.executable,
                args=("-c", "print('nope')"),
                cwd="..",
                revision=REVISION,
            )
        env_result = tool.run(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            program=sys.executable,
            args=(
                "-c",
                "import os; print(os.getenv('OPENAI_API_KEY')); "
                "print('PATH=' + str(bool(os.getenv('PATH'))))",
            ),
            cwd=".",
            revision=REVISION,
        )
        timeout_result = tool.run(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            program=sys.executable,
            args=("-c", "import time; time.sleep(2)"),
            cwd=".",
            revision=REVISION,
            timeout_seconds=0.1,
        )
        executions = session.query(ToolExecution).all()

    assert "sk-proj" not in env_result.stdout
    assert "PATH=True" in env_result.stdout
    assert timeout_result.timed_out is True
    assert timeout_result.exit_code is None
    assert len(executions) == 2
