from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.api import diffs
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.main import create_app
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
from se_mentor.models.task import ChangeTask, TaskStatus


def test_task_file_changes_are_task_scoped_and_use_persisted_tool_diff(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "task-file-changes.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    diffs._SESSION_FACTORY = session_factory

    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("value = 3\n", encoding="utf-8")
    backup_path = tmp_path / "backup-app.py"
    backup_path.write_text("value = 1\n", encoding="utf-8")
    diff_text = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.COMPLETED
        lock = WorkspaceLock(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            lock_mode=WorkspaceLockMode.WRITE,
            status=WorkspaceLockStatus.ACTIVE,
            owner="test",
            reason="seed committed transaction",
        )
        session.add(lock)
        session.flush()
        transaction = TaskTransaction(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            workspace_lock_id=lock.id,
            state=TransactionState.COMMITTED,
            manifest_artifact_ref=str(tmp_path / "manifest.json"),
        )
        session.add(transaction)
        session.flush()
        tool = ToolExecution(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=transaction.id,
            tool_name="APPLY_PATCH",
            command_summary="apply patch app.py",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps({"relative_path": "app.py", "diff": diff_text}),
        )
        session.add(tool)
        session.flush()
        backup = BackupEntry(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            original_hash="a" * 64,
            backup_artifact_ref=str(backup_path),
            file_type="text/plain",
            relative_path="app.py",
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
                relative_path="app.py",
                before_hash="a" * 64,
                after_hash="b" * 64,
            )
        )

    client = TestClient(create_app())
    diffs._SESSION_FACTORY = session_factory
    response = client.get(f"/api/diffs/tasks/{ids['task_id']}/changes")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["taskId"] == ids["task_id"]
    assert payload["count"] == 1
    assert payload["items"][0]["relativePath"] == "app.py"
    assert payload["items"][0]["transactionId"] == transaction.id
    assert payload["items"][0]["diff"] == diff_text
    assert "+value = 3" not in payload["items"][0]["diff"]
