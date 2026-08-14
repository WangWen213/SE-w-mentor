from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

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
from se_mentor.paths import ProjectPathError, canonical_project_path
from se_mentor.policy.grants import ExecutionAuthorization, TemporaryGrant


class DeleteFileError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeleteFileResult:
    relative_path: str
    deleted: bool
    before_sha256: str | None
    backup_ref: str | None
    tool_execution_id: str


class DeleteFileTool:
    def __init__(self, session: Session, *, project_root: str | Path) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()

    def delete(
        self,
        *,
        task_id: str,
        action_id: str,
        transaction_id: str,
        grant: TemporaryGrant | ExecutionAuthorization,
        relative_path: str,
        revision: str,
    ) -> DeleteFileResult:
        transaction = self._prepared_transaction(transaction_id, task_id)
        normalized = _normalize_relative_path(relative_path)
        if not grant.allows_write(normalized, revision=revision):
            raise DeleteFileError("matching grant required")
        target = (self.project_root / normalized).resolve()
        if not target.is_relative_to(self.project_root) or target == self.project_root:
            raise DeleteFileError("target path invalid")
        if not target.exists():
            raise DeleteFileError("target path not found")
        if target.is_dir():
            raise DeleteFileError("recursive delete is not supported")

        before_bytes = target.read_bytes()
        before_hash = _sha(before_bytes)
        backup_path = _backup_file(transaction, target, normalized)
        target.unlink()
        tool_execution = self._record_execution(
            task_id,
            action_id,
            transaction.id,
            normalized,
            "deleted",
        )
        backup = BackupEntry(
            task_id=task_id,
            project_id=transaction.project_id,
            original_hash=before_hash,
            backup_artifact_ref=str(backup_path),
            file_type="application/octet-stream",
            relative_path=normalized,
        )
        self.session.add(backup)
        self.session.flush()
        self.session.add(
            FileChange(
                task_id=task_id,
                tool_execution_id=tool_execution.id,
                action_id=action_id,
                backup_entry_id=backup.id,
                change_type=FileChangeType.DELETE,
                relative_path=normalized,
                before_hash=before_hash,
                after_hash=None,
            )
        )
        self.session.flush()
        return DeleteFileResult(normalized, True, before_hash, str(backup_path), tool_execution.id)

    def _prepared_transaction(self, transaction_id: str, task_id: str) -> TaskTransaction:
        transaction = self.session.get(TaskTransaction, transaction_id)
        if (
            transaction is None
            or transaction.task_id != task_id
            or transaction.state != TransactionState.PREPARED
            or transaction.manifest_artifact_ref is None
        ):
            raise DeleteFileError("prepared transaction required")
        return transaction

    def _record_execution(
        self,
        task_id: str,
        action_id: str,
        transaction_id: str,
        relative_path: str,
        result: str,
    ) -> ToolExecution:
        execution = ToolExecution(
            task_id=task_id,
            action_id=action_id,
            transaction_id=transaction_id,
            tool_name="DELETE_FILE",
            command_summary=f"delete file {relative_path}",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps({"relative_path": relative_path, "result": result}),
        )
        self.session.add(execution)
        self.session.flush()
        return execution


def _normalize_relative_path(relative_path: str) -> str:
    try:
        return canonical_project_path(relative_path)
    except ProjectPathError as exc:
        raise DeleteFileError("target path invalid") from exc


def _backup_file(transaction: TaskTransaction, target: Path, relative_path: str) -> Path:
    manifest_path = Path(str(transaction.manifest_artifact_ref))
    backup_path = manifest_path.parent / "deleted-files" / relative_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_bytes(target.read_bytes())
    return backup_path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
