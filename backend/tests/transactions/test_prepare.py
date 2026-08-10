from __future__ import annotations

import json
from pathlib import Path

import pytest
from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.execution import TaskTransaction, TransactionState, WorkspaceLockMode
from se_mentor.transactions.manager import TransactionManager, TransactionPrepareError
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_T058_side_effect_requires_active_lock_transaction_and_baseline_manifest(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "prepare.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    dirty = repo / "user_notes.txt"
    dirty.write_text("pre-existing user edit", encoding="utf-8")
    backup_root = tmp_path / "mentor-backups"
    lock_result = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="prepare side effect",
    )
    assert lock_result.lock is not None

    with session_scope(session_factory) as session:
        manager = TransactionManager(session, backup_root=backup_root)
        with pytest.raises(TransactionPrepareError, match="active WRITE lock"):
            manager.prepare(
                task_id=ids["task_id"],
                project_id=ids["project_id"],
                lock_id="missing-lock",
                expected_base_revision=REVISION,
            )
        assert session.query(TaskTransaction).count() == 0
        assert not backup_root.exists()

        with pytest.raises(TransactionPrepareError, match="baseRevision"):
            manager.prepare(
                task_id=ids["task_id"],
                project_id=ids["project_id"],
                lock_id=lock_result.lock.id,
                expected_base_revision="stale-revision",
            )
        assert session.query(TaskTransaction).count() == 0

        prepared = manager.prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock_result.lock.id,
            expected_base_revision=REVISION,
        )
        repeated = manager.prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock_result.lock.id,
            expected_base_revision=REVISION,
        )

    assert prepared.transaction_id == repeated.transaction_id
    assert prepared.state == TransactionState.PREPARED
    assert prepared.backup_dir.exists()
    assert prepared.backup_dir.is_dir()
    assert not prepared.backup_dir.is_relative_to(repo)
    assert prepared.manifest_path.exists()
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["task_id"] == ids["task_id"]
    assert manifest["project_id"] == ids["project_id"]
    assert manifest["lock_id"] == lock_result.lock.id
    assert manifest["base_revision"] == REVISION
    assert manifest["workspace_state"] == "DIRTY"
    assert manifest["preexisting_changes"] == [
        {"path": "user_notes.txt", "sha256": prepared.file_hashes["user_notes.txt"]}
    ]
    assert manifest["backup_dir"] == str(prepared.backup_dir)
