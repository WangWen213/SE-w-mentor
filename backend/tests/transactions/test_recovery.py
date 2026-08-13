from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.audit import AlertEvent, AlertStatus, AuditEvent
from se_mentor.models.execution import TaskTransaction, TransactionState, WorkspaceLockMode
from se_mentor.transactions.manager import TransactionManager
from se_mentor.transactions.recovery import RecoveryDecision, TransactionRecoveryService
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService


def test_T065_restart_detects_unfinished_transaction_and_blocks_new_writer(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "recovery.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other = seed_task_graph(engine, tmp_path / "other")
    repo = tmp_path / "repo"
    repo.mkdir()
    external = repo / "external.py"
    external.write_text("before restart\n", encoding="utf-8")
    session_factory = create_session_factory(engine)
    lock_service = WorkspaceLockService(session_factory)
    acquired = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-before-crash",
        reason="prepare interrupted transaction",
    )
    assert acquired.lock is not None

    with session_scope(session_factory) as session:
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=acquired.lock.id,
            expected_base_revision=REVISION,
        )
        transaction = session.get(TaskTransaction, prepared.transaction_id)
        assert transaction is not None
        transaction.state = TransactionState.APPLYING
        external.write_text("changed after crash\n", encoding="utf-8")
        recovery = TransactionRecoveryService(session, project_root=repo)
        summaries = recovery.scan_project(project_id=ids["project_id"])

    blocked = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=other["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="new-writer",
        reason="should block until recovery",
    )
    assert blocked.status is LockAcquireStatus.RECOVERY_REQUIRED
    assert summaries[0].transaction_id == prepared.transaction_id
    assert summaries[0].decision == RecoveryDecision.MANUAL
    assert summaries[0].external_changes == ("external.py",)

    external.write_text("before restart\n", encoding="utf-8")
    with session_scope(session_factory) as session:
        recovery = TransactionRecoveryService(session, project_root=repo)
        result = recovery.resolve_by_rollback(
            task_id=ids["task_id"],
            transaction_id=prepared.transaction_id,
        )
        transaction = session.get(TaskTransaction, prepared.transaction_id)
        assert transaction is not None
        alerts = session.query(AlertEvent).all()
        audits = session.query(AuditEvent).all()

    assert result.resolved is True
    assert transaction.state == TransactionState.ROLLED_BACK
    assert alerts
    assert alerts[-1].status == AlertStatus.RESOLVED
    assert len(audits) >= 2

    released = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=other["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="new-writer",
        reason="recovery complete",
    )
    assert released.status is LockAcquireStatus.ACQUIRED
