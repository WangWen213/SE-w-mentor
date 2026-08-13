from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.api import tasks
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


def test_task_timeline_projects_authoritative_execution_facts(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "task-timeline.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    tasks._SESSION_FACTORY = session_factory

    diff_text = (
        "--- a/frontend/src/app/fixtures.ts\n"
        "+++ b/frontend/src/app/fixtures.ts\n"
        "@@ -1 +1 @@\n"
        '-  { key: "tasks", label: "\\u4efb\\u52a17", marker: "T" },\n'
        '+  { key: "tasks", label: "\\u4efb\\u52a18", marker: "T" },\n'
    )
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
            reason="seed timeline transaction",
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
        search_tool = ToolExecution(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="SEARCH_CODE",
            command_summary="SEARCH_CODE",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps(
                {
                    "result": {
                        "matches": [
                            {"path": "frontend/src/app/fixtures.ts", "line": 72},
                        ],
                    },
                }
            ),
        )
        session.add(search_tool)
        session.flush()
        write_tool = ToolExecution(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=transaction.id,
            tool_name="APPLY_PATCH",
            command_summary="apply patch frontend/src/app/fixtures.ts",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps({"diff": diff_text}),
        )
        session.add(write_tool)
        session.flush()
        backup = BackupEntry(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            original_hash="a" * 64,
            backup_artifact_ref=str(tmp_path / "fixtures.ts"),
            file_type="text/plain",
            relative_path="frontend/src/app/fixtures.ts",
        )
        session.add(backup)
        session.flush()
        session.add(
            FileChange(
                task_id=ids["task_id"],
                tool_execution_id=write_tool.id,
                action_id=ids["action_id"],
                backup_entry_id=backup.id,
                change_type=FileChangeType.MODIFY,
                relative_path="frontend/src/app/fixtures.ts",
                before_hash="a" * 64,
                after_hash="b" * 64,
            )
        )

    client = TestClient(create_app())
    tasks._SESSION_FACTORY = session_factory
    response = client.get(f"/api/tasks/{ids['task_id']}/timeline")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["taskId"] == ids["task_id"]
    kinds = [item["kind"] for item in payload["items"]]
    assert "PROPOSAL_READY" in kinds
    assert "PROPOSAL_CONFIRMED" in kinds
    assert "GOVERNANCE_APPROVAL_REQUIRED" in kinds
    assert "GOVERNANCE_BLOCK" in kinds
    assert "TARGET_LOCATED" in kinds
    assert "EXECUTION_STARTED" in kinds
    assert "FILE_CHANGED" in kinds
    assert "TASK_COMPLETED" in kinds
    file_node = next(item for item in payload["items"] if item["kind"] == "FILE_CHANGED")
    assert file_node["source"]["type"] == "FileChange"
    assert "frontend/src/app/fixtures.ts" in file_node["body"]
    assert "任务7 -> 任务8" in file_node["body"]
    assert file_node["action"] == {"label": "查看改动", "target": "changes"}
