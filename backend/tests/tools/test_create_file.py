from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import FileChange, FileChangeType, ToolExecution, WorkspaceLockMode
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.create_file import CreateFileError, CreateFileTool
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_T060_create_existing_or_unapproved_file_is_rejected(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "create-file.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="create file",
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
            read_paths_json='["src/new.py"]',
            write_paths_json='["src/new.py"]',
            protected_paths_json='[".env"]',
            commands_json="[]",
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":30}',
            invalidation_json='{"proposal_hash":"aaaaaaaa"}',
            evidence_json='[{"source":"test"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("src/new.py",),
            commands=(),
        )
        tool = CreateFileTool(session, project_root=repo)

        with pytest.raises(CreateFileError, match="policy scope"):
            tool.create(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                relative_path="src/other.py",
                content="blocked\n",
                revision=REVISION,
            )
        result = tool.create(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            relative_path="src/new.py",
            content="created = True\n",
            revision=REVISION,
        )
        with pytest.raises(CreateFileError, match="existing file"):
            tool.create(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                relative_path="src/new.py",
                content="overwrite = True\n",
                revision=REVISION,
            )
        changes = session.query(FileChange).all()
        executions = session.query(ToolExecution).all()

    assert not (repo / "src" / "other.py").exists()
    assert (repo / "src" / "new.py").read_text(encoding="utf-8") == "created = True\n"
    assert result.relative_path == "src/new.py"
    assert result.rollback_delete_path == "src/new.py"
    assert len(changes) == 1
    assert changes[0].change_type == FileChangeType.CREATE
    assert changes[0].before_hash is None
    assert changes[0].after_hash == result.after_sha256
    assert len(executions) == 1
    assert executions[0].transaction_id == prepared.transaction_id
