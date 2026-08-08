from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.audit import AlertEvent, AuditEvent
from se_mentor.models.execution import (
    TaskTransaction,
    TransactionState,
    WorkspaceLock,
    WorkspaceLockMode,
    WorkspaceLockStatus,
)
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService


def test_T023_expired_lock_with_unfinished_transaction_blocks_new_writer(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "lifecycle.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)
    service = WorkspaceLockService(session_factory)

    acquired = service.acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="owner",
        reason="edit",
        ttl_seconds=1,
    )
    assert acquired.lock is not None
    lock_id = acquired.lock.id

    with session_scope(session_factory) as session:
        lock = service.heartbeat(lock_id, expected_version=1, session=session)
        assert lock.version == 2
        stored_lock = session.get(WorkspaceLock, lock_id)
        assert stored_lock is not None
        stored_lock.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        transaction = TaskTransaction(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            workspace_lock_id=lock_id,
            state=TransactionState.APPLYING,
            manifest_artifact_ref=None,
        )
        session.add(transaction)

    blocked = service.acquire(
        project_id=ids["project_id"],
        task_id=other["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="next-owner",
        reason="edit",
    )
    assert blocked.status is LockAcquireStatus.RECOVERY_REQUIRED
    assert blocked.transaction_created is False

    with session_scope(session_factory) as session:
        assert session.query(AlertEvent).count() == 1
        assert session.query(AuditEvent).count() == 1
        lock = service.force_release(
            lock_id,
            actor_id="operator",
            reason="manual recovery completed",
            session=session,
        )
        assert lock.status == WorkspaceLockStatus.RELEASED
        released_lock = session.get(WorkspaceLock, lock_id)
        assert released_lock is not None
        assert released_lock.released_at is not None
        assert session.query(AuditEvent).count() == 2
