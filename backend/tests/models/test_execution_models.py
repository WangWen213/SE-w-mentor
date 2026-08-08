from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, execute, seed_task_graph
from sqlalchemy import exc

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.execution import (
    BackupEntry,
    FileChange,
    FileChangeType,
    TaskTransaction,
    ToolExecution,
    ToolExecutionStatus,
    TransactionState,
    WorkspaceLock,
    WorkspaceLockMode,
    WorkspaceLockStatus,
)


def test_T014_committed_transaction_requires_manifest_and_active_write_lock(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "execution.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO task_transactions (
                id, task_id, project_id, state, manifest_artifact_ref, created_at, updated_at
            )
            VALUES (
                'bad-committed', :task_id, :project_id, 'COMMITTED', NULL,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"task_id": ids["task_id"], "project_id": ids["project_id"]},
        )

    with session_scope(session_factory) as session:
        lock = WorkspaceLock(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            lock_mode=WorkspaceLockMode.WRITE,
            status=WorkspaceLockStatus.ACTIVE,
            owner="codex",
            reason="schema write",
        )
        session.add(lock)
        session.flush()
        transaction = TaskTransaction(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            workspace_lock_id=lock.id,
            state=TransactionState.COMMITTED,
            manifest_artifact_ref="artifact://manifest.json",
        )
        session.add(transaction)
        session.flush()
        transaction_id = transaction.id

    with session_scope(session_factory) as session:
        assert session.get(TaskTransaction, transaction_id) is not None


def test_T014_single_active_write_lock_and_file_change_traceability(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "file-change.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        lock = WorkspaceLock(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            lock_mode=WorkspaceLockMode.WRITE,
            status=WorkspaceLockStatus.ACTIVE,
            owner="codex",
            reason="schema write",
        )
        session.add(lock)
        session.flush()
        tool = ToolExecution(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=None,
            tool_name="apply_patch",
            command_summary="apply patch",
            status=ToolExecutionStatus.SUCCEEDED,
            exit_code=0,
            started_at=None,
            finished_at=None,
            evidence_json='[{"source":"T014","summary":"tool"}]',
        )
        session.add(tool)
        session.flush()
        backup = BackupEntry(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            original_hash="a" * 64,
            backup_artifact_ref="artifact://backup/file.py",
            file_type="text/x-python",
            relative_path="backend/src/example.py",
        )
        session.add(backup)
        session.flush()
        session.add(
            FileChange(
                task_id=ids["task_id"],
                tool_execution_id=tool.id,
                action_id=ids["action_id"],
                backup_entry_id=backup.id,
                change_type=FileChangeType.MODIFY,
                relative_path="backend/src/example.py",
                before_hash="a" * 64,
                after_hash="b" * 64,
            )
        )
        session.flush()

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO workspace_locks (
                id, project_id, task_id, lock_mode, status, owner, reason, created_at
            )
            VALUES (
                'second-write-lock', :project_id, :task_id, 'WRITE', 'ACTIVE',
                'codex', 'duplicate', CURRENT_TIMESTAMP
            )
            """,
            {"project_id": ids["project_id"], "task_id": ids["task_id"]},
        )

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO file_changes (
                id, task_id, tool_execution_id, action_id, change_type, relative_path,
                created_at
            )
            VALUES (
                'bad-file-change', :task_id, 'missing-tool', :action_id, 'MODIFY',
                'backend/src/example.py', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": ids["task_id"], "action_id": ids["action_id"]},
        )
