from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.contracts.enums import EventType
from se_mentor.db.session import session_scope
from se_mentor.models.audit import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    AuditActorType,
    AuditEvent,
)
from se_mentor.models.execution import (
    TaskTransaction,
    TransactionState,
    WorkspaceLock,
    WorkspaceLockMode,
    WorkspaceLockStatus,
)


class LockAcquireStatus(StrEnum):
    ACQUIRED = "ACQUIRED"
    CONFLICT = "CONFLICT"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class LockSnapshot:
    id: str
    status: str
    version: int


@dataclass(frozen=True)
class LockAcquireResult:
    status: LockAcquireStatus
    lock: LockSnapshot | None = None
    transaction_created: bool = False


_LOCK_GUARD = threading.Lock()


class WorkspaceLockService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def acquire(
        self,
        *,
        project_id: str,
        task_id: str,
        mode: WorkspaceLockMode,
        owner_instance: str,
        reason: str,
        ttl_seconds: int = 300,
        session: Session | None = None,
    ) -> LockAcquireResult:
        if session is not None:
            return self._acquire_in_session(
                session, project_id, task_id, mode, owner_instance, reason, ttl_seconds
            )
        with _LOCK_GUARD, session_scope(self._session_factory) as owned_session:
            return self._acquire_in_session(
                owned_session, project_id, task_id, mode, owner_instance, reason, ttl_seconds
            )

    def heartbeat(
        self,
        lock_id: str,
        *,
        expected_version: int,
        session: Session,
        ttl_seconds: int = 300,
    ) -> LockSnapshot:
        lock = session.get(WorkspaceLock, lock_id)
        if lock is None or lock.status != WorkspaceLockStatus.ACTIVE:
            raise ValueError("active lock not found")
        current_version = _version(lock)
        if current_version != expected_version:
            raise ValueError("lock version conflict")
        _set_version(lock, current_version + 1)
        lock.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        session.flush()
        return LockSnapshot(lock.id, lock.status, _version(lock))

    def force_release(
        self,
        lock_id: str,
        *,
        actor_id: str,
        reason: str,
        session: Session,
    ) -> LockSnapshot:
        lock = session.get(WorkspaceLock, lock_id)
        if lock is None:
            raise ValueError("lock not found")
        lock.status = WorkspaceLockStatus.RELEASED
        lock.released_at = datetime.now(UTC)
        _set_version(lock, _version(lock) + 1)
        session.add(
            AuditEvent(
                task_id=lock.task_id,
                correlation_id=f"lock:{lock.id}:force-release",
                actor_type=AuditActorType.USER,
                actor_id=actor_id,
                event_type=EventType.TOOL_EXECUTED,
                payload_summary="workspace lock force released",
                evidence_json=json.dumps({"reason": reason, "lock_id": lock.id}),
            )
        )
        session.flush()
        return LockSnapshot(lock.id, lock.status, _version(lock))

    def _acquire_in_session(
        self,
        session: Session,
        project_id: str,
        task_id: str,
        mode: WorkspaceLockMode,
        owner_instance: str,
        reason: str,
        ttl_seconds: int,
    ) -> LockAcquireResult:
        self._mark_expired(session, project_id)
        if self._requires_recovery(session, project_id):
            _emit_recovery_audit(session, task_id, project_id)
            return LockAcquireResult(LockAcquireStatus.RECOVERY_REQUIRED, transaction_created=False)
        active = session.scalars(
            select(WorkspaceLock).where(
                WorkspaceLock.project_id == project_id,
                WorkspaceLock.status == WorkspaceLockStatus.ACTIVE,
            )
        ).all()
        if mode == WorkspaceLockMode.WRITE and active:
            return LockAcquireResult(LockAcquireStatus.CONFLICT)
        if mode == WorkspaceLockMode.READ and any(
            lock.lock_mode == WorkspaceLockMode.WRITE for lock in active
        ):
            return LockAcquireResult(LockAcquireStatus.CONFLICT)
        lock = WorkspaceLock(
            project_id=project_id,
            task_id=task_id,
            lock_mode=mode,
            status=WorkspaceLockStatus.ACTIVE,
            owner=f"{owner_instance};version=1",
            reason=reason,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        session.add(lock)
        session.flush()
        return LockAcquireResult(
            LockAcquireStatus.ACQUIRED,
            LockSnapshot(lock.id, lock.status, _version(lock)),
            transaction_created=False,
        )

    def _mark_expired(self, session: Session, project_id: str) -> None:
        now = datetime.now(UTC)
        locks = session.scalars(
            select(WorkspaceLock).where(
                WorkspaceLock.project_id == project_id,
                WorkspaceLock.status == WorkspaceLockStatus.ACTIVE,
                WorkspaceLock.expires_at.is_not(None),
            )
        ).all()
        for lock in locks:
            expires_at = lock.expires_at
            if expires_at is not None and _as_aware(expires_at) < now:
                lock.status = WorkspaceLockStatus.EXPIRED
        session.flush()

    def _requires_recovery(self, session: Session, project_id: str) -> bool:
        unfinished_without_recovery = session.scalars(
            select(TaskTransaction).where(
                TaskTransaction.project_id == project_id,
                TaskTransaction.state.in_([TransactionState.PREPARED, TransactionState.APPLYING]),
            )
        ).first()
        if unfinished_without_recovery is not None:
            return True
        expired_locks = session.scalars(
            select(WorkspaceLock).where(
                WorkspaceLock.project_id == project_id,
                WorkspaceLock.status == WorkspaceLockStatus.EXPIRED,
            )
        ).all()
        if not expired_locks:
            return False
        expired_ids = [lock.id for lock in expired_locks]
        unfinished = session.scalars(
            select(TaskTransaction).where(
                TaskTransaction.workspace_lock_id.in_(expired_ids),
                TaskTransaction.state.in_([TransactionState.PREPARED, TransactionState.APPLYING]),
            )
        ).first()
        return unfinished is not None


def _emit_recovery_audit(session: Session, task_id: str, project_id: str) -> None:
    exists = session.scalar(
        select(AlertEvent).where(
            AlertEvent.task_id == task_id,
            AlertEvent.summary == "workspace lock recovery required",
        )
    )
    if exists is not None:
        return
    evidence = json.dumps({"project_id": project_id, "reason": "unfinished transaction"})
    session.add(
        AlertEvent(
            task_id=task_id,
            system_scope=False,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.OPEN,
            summary="workspace lock recovery required",
            evidence_json=evidence,
        )
    )
    session.add(
        AuditEvent(
            task_id=task_id,
            correlation_id=f"lock-recovery:{task_id}",
            actor_type=AuditActorType.SYSTEM,
            actor_id="workspace-lock-service",
            event_type=EventType.TOOL_EXECUTED,
            payload_summary="workspace lock recovery required",
            evidence_json=evidence,
        )
    )
    session.flush()


def _version(lock: WorkspaceLock) -> int:
    marker = "version="
    if marker not in lock.owner:
        return 1
    return int(lock.owner.rsplit(marker, 1)[1])


def _set_version(lock: WorkspaceLock, version: int) -> None:
    owner = lock.owner.split(";version=", 1)[0]
    lock.owner = f"{owner};version={version}"


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
