from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.contracts.enums import EventType
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
    WorkspaceLockStatus,
)
from se_mentor.transactions.rollback import RollbackResult, TransactionRollbackService


class RecoveryDecision(StrEnum):
    AUTO_ROLLBACK = "AUTO_ROLLBACK"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class RecoverySummary:
    transaction_id: str
    task_id: str
    decision: RecoveryDecision
    external_changes: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryResolution:
    transaction_id: str
    resolved: bool
    rollback: RollbackResult


class TransactionRecoveryService:
    def __init__(self, session: Session, *, project_root: str | Path) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()

    def scan_project(self, *, project_id: str) -> tuple[RecoverySummary, ...]:
        summaries: list[RecoverySummary] = []
        transactions = self.session.scalars(
            select(TaskTransaction).where(
                TaskTransaction.project_id == project_id,
                TaskTransaction.state.in_(
                    [
                        TransactionState.PREPARED,
                        TransactionState.APPLYING,
                        TransactionState.CONFLICT,
                    ]
                ),
            )
        ).all()
        for transaction in transactions:
            external_changes = self._external_changes(transaction)
            decision = (
                RecoveryDecision.MANUAL if external_changes else RecoveryDecision.AUTO_ROLLBACK
            )
            self._emit_recovery_events(transaction, decision, external_changes)
            summaries.append(
                RecoverySummary(
                    transaction.id,
                    transaction.task_id,
                    decision,
                    external_changes,
                )
            )
        self.session.flush()
        return tuple(summaries)

    def resolve_by_rollback(self, *, task_id: str, transaction_id: str) -> RecoveryResolution:
        rollback = TransactionRollbackService(
            self.session, project_root=self.project_root
        ).rollback(
            task_id=task_id,
            transaction_id=transaction_id,
        )
        transaction = self.session.get(TaskTransaction, transaction_id)
        if transaction is None:
            raise ValueError("transaction not found")
        lock = (
            self.session.get(WorkspaceLock, transaction.workspace_lock_id)
            if transaction.workspace_lock_id is not None
            else None
        )
        if lock is not None and lock.status == WorkspaceLockStatus.ACTIVE:
            lock.status = WorkspaceLockStatus.RELEASED
            lock.released_at = datetime.now(UTC)
        for alert in self.session.scalars(
            select(AlertEvent).where(
                AlertEvent.summary.in_(
                    [
                        "transaction recovery required",
                        "workspace lock recovery required",
                    ]
                ),
                AlertEvent.status == AlertStatus.OPEN,
            )
        ):
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(UTC)
        self.session.add(
            AuditEvent(
                task_id=task_id,
                correlation_id=f"transaction-recovery-resolved:{transaction_id}",
                actor_type=AuditActorType.SYSTEM,
                actor_id="transaction-recovery-service",
                event_type=EventType.TOOL_EXECUTED,
                payload_summary="transaction recovery resolved by rollback",
                evidence_json=json.dumps({"transaction_id": transaction_id}),
            )
        )
        self.session.flush()
        return RecoveryResolution(transaction_id, True, rollback)

    def _external_changes(self, transaction: TaskTransaction) -> tuple[str, ...]:
        if transaction.manifest_artifact_ref is None:
            return ()
        manifest_path = Path(transaction.manifest_artifact_ref)
        if not manifest_path.exists():
            return ()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed: list[str] = []
        for item in manifest.get("preexisting_changes", []):
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("path", ""))
            expected = str(item.get("sha256", ""))
            target = (self.project_root / relative_path).resolve()
            if not target.is_relative_to(self.project_root):
                continue
            current = _sha(target.read_bytes()) if target.is_file() else ""
            if expected and current != expected:
                changed.append(relative_path)
        return tuple(sorted(changed))

    def _emit_recovery_events(
        self,
        transaction: TaskTransaction,
        decision: RecoveryDecision,
        external_changes: tuple[str, ...],
    ) -> None:
        evidence = json.dumps(
            {
                "transaction_id": transaction.id,
                "decision": decision,
                "external_changes": external_changes,
            },
            sort_keys=True,
        )
        existing = self.session.scalar(
            select(AlertEvent).where(
                AlertEvent.task_id == transaction.task_id,
                AlertEvent.summary == "transaction recovery required",
                AlertEvent.status == AlertStatus.OPEN,
            )
        )
        if existing is None:
            self.session.add(
                AlertEvent(
                    task_id=transaction.task_id,
                    system_scope=False,
                    severity=AlertSeverity.HIGH,
                    status=AlertStatus.OPEN,
                    summary="transaction recovery required",
                    evidence_json=evidence,
                )
            )
        self.session.add(
            AuditEvent(
                task_id=transaction.task_id,
                correlation_id=f"transaction-recovery:{transaction.id}",
                actor_type=AuditActorType.SYSTEM,
                actor_id="transaction-recovery-service",
                event_type=EventType.TOOL_EXECUTED,
                payload_summary="transaction recovery required",
                evidence_json=evidence,
            )
        )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
