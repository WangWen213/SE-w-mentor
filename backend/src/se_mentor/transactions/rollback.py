from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.execution import (
    BackupEntry,
    FileChange,
    FileChangeType,
    TaskTransaction,
    ToolExecution,
    ToolExecutionStatus,
    TransactionState,
)
from se_mentor.models.llm import AgentAction


class RollbackError(RuntimeError):
    pass


class RollbackConflict(RollbackError):
    pass


@dataclass(frozen=True)
class RollbackResult:
    transaction_id: str
    rolled_back: bool
    restored_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]


class TransactionRollbackService:
    def __init__(self, session: Session, *, project_root: str | Path) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()

    def rollback(self, *, task_id: str, transaction_id: str) -> RollbackResult:
        transaction = self.session.get(TaskTransaction, transaction_id)
        if transaction is None or transaction.task_id != task_id:
            raise RollbackError("transaction not found")
        if transaction.state == TransactionState.ROLLED_BACK:
            return RollbackResult(transaction.id, False, (), ())
        if transaction.state not in {
            TransactionState.PREPARED,
            TransactionState.APPLYING,
            TransactionState.CONFLICT,
        }:
            raise RollbackError("transaction state cannot be rolled back")

        restored: list[str] = []
        deleted: list[str] = []
        changes = self._changes(task_id, transaction_id)
        try:
            for change in reversed(changes):
                if change.change_type == FileChangeType.CREATE:
                    self._rollback_create(change)
                    deleted.append(change.relative_path)
                elif change.change_type in {FileChangeType.MODIFY, FileChangeType.DELETE}:
                    self._restore_backup(change)
                    restored.append(change.relative_path)
                else:
                    raise RollbackError(f"unsupported change type {change.change_type}")
        except RollbackConflict:
            transaction.state = TransactionState.CONFLICT
            self.session.flush()
            raise

        transaction.state = TransactionState.ROLLED_BACK
        self._record(task_id, transaction.id, restored, deleted)
        self.session.flush()
        return RollbackResult(transaction.id, True, tuple(restored), tuple(deleted))

    def _changes(self, task_id: str, transaction_id: str) -> tuple[FileChange, ...]:
        return tuple(
            self.session.scalars(
                select(FileChange)
                .join(ToolExecution, ToolExecution.id == FileChange.tool_execution_id)
                .where(
                    FileChange.task_id == task_id,
                    ToolExecution.transaction_id == transaction_id,
                )
                .order_by(FileChange.created_at, FileChange.id)
            )
        )

    def _rollback_create(self, change: FileChange) -> None:
        target = self._target(change.relative_path)
        if not target.exists():
            return
        if not target.is_file():
            raise RollbackConflict(f"current hash conflict for {change.relative_path}")
        current_hash = _sha(target.read_bytes())
        if change.after_hash is not None and current_hash != change.after_hash:
            raise RollbackConflict(f"current hash conflict for {change.relative_path}")
        target.unlink()

    def _restore_backup(self, change: FileChange) -> None:
        backup = self._backup(change)
        target = self._target(change.relative_path)
        backup_bytes = Path(backup.backup_artifact_ref).read_bytes()
        if target.exists():
            if not target.is_file():
                raise RollbackConflict(f"current hash conflict for {change.relative_path}")
            current_hash = _sha(target.read_bytes())
            if current_hash == backup.original_hash:
                return
            expected_agent_hash = (
                change.after_hash
                if change.change_type == FileChangeType.MODIFY
                else change.before_hash
            )
            if expected_agent_hash is not None and current_hash != expected_agent_hash:
                raise RollbackConflict(f"current hash conflict for {change.relative_path}")
        elif change.change_type == FileChangeType.MODIFY:
            raise RollbackConflict(f"current hash conflict for {change.relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(backup_bytes)

    def _backup(self, change: FileChange) -> BackupEntry:
        if change.backup_entry_id is None:
            raise RollbackError("backup entry required")
        backup = self.session.get(BackupEntry, change.backup_entry_id)
        if backup is None:
            raise RollbackError("backup entry missing")
        return backup

    def _target(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise RollbackError("target path invalid")
        target = (self.project_root / path).resolve()
        if not target.is_relative_to(self.project_root):
            raise RollbackError("target path invalid")
        return target

    def _record(
        self,
        task_id: str,
        transaction_id: str,
        restored: list[str],
        deleted: list[str],
    ) -> None:
        self.session.add(
            ToolExecution(
                task_id=task_id,
                action_id=self._rollback_action_id(task_id, transaction_id),
                transaction_id=transaction_id,
                tool_name="ROLLBACK",
                command_summary="rollback transaction",
                status=ToolExecutionStatus.SUCCEEDED,
                evidence_json=json.dumps(
                    {"restored_paths": restored, "deleted_paths": deleted},
                    sort_keys=True,
                ),
            )
        )

    def _rollback_action_id(self, task_id: str, transaction_id: str) -> str:
        execution = self.session.scalar(
            select(ToolExecution)
            .where(
                ToolExecution.task_id == task_id,
                ToolExecution.transaction_id == transaction_id,
            )
            .order_by(ToolExecution.created_at, ToolExecution.id)
        )
        if execution is not None:
            return execution.action_id
        action = self.session.scalar(
            select(AgentAction).where(AgentAction.task_id == task_id).order_by(AgentAction.id)
        )
        if action is None:
            raise RollbackError("agent action required")
        return action.id


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
