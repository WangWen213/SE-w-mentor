from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from se_mentor.models.execution import (
    FileChange,
    FileChangeType,
    TaskTransaction,
    ToolExecution,
    ToolExecutionStatus,
    TransactionState,
)
from se_mentor.paths import ProjectPathError, canonical_project_path
from se_mentor.policy.grants import ExecutionAuthorization, TemporaryGrant


class CreateFileError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreateFileResult:
    relative_path: str
    after_sha256: str
    rollback_delete_path: str
    tool_execution_id: str


class CreateFileTool:
    def __init__(self, session: Session, *, project_root: str | Path) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()

    def create(
        self,
        *,
        task_id: str,
        action_id: str,
        transaction_id: str,
        grant: TemporaryGrant | ExecutionAuthorization,
        relative_path: str,
        content: str,
        revision: str,
    ) -> CreateFileResult:
        transaction = self._prepared_transaction(transaction_id, task_id)
        normalized = _normalize_relative_path(relative_path)
        if not grant.allows_write(normalized, revision=revision):
            raise CreateFileError("policy scope denied")
        target = (self.project_root / normalized).resolve()
        if not target.is_relative_to(self.project_root):
            raise CreateFileError("target path invalid")
        if not target.parent.is_dir() or not target.parent.is_relative_to(self.project_root):
            raise CreateFileError("parent directory denied")
        if target.exists():
            raise CreateFileError("existing file")

        try:
            with target.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except FileExistsError as exc:
            raise CreateFileError("existing file") from exc

        after_hash = _sha(target.read_bytes())
        tool_execution = ToolExecution(
            task_id=task_id,
            action_id=action_id,
            transaction_id=transaction.id,
            tool_name="CREATE_FILE",
            command_summary=f"create file {normalized}",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps(
                {"relative_path": normalized, "rollback": {"delete_created_file": normalized}},
                sort_keys=True,
            ),
        )
        self.session.add(tool_execution)
        self.session.flush()
        self.session.add(
            FileChange(
                task_id=task_id,
                tool_execution_id=tool_execution.id,
                action_id=action_id,
                backup_entry_id=None,
                change_type=FileChangeType.CREATE,
                relative_path=normalized,
                before_hash=None,
                after_hash=after_hash,
            )
        )
        self.session.flush()
        return CreateFileResult(normalized, after_hash, normalized, tool_execution.id)

    def _prepared_transaction(self, transaction_id: str, task_id: str) -> TaskTransaction:
        transaction = self.session.get(TaskTransaction, transaction_id)
        if (
            transaction is None
            or transaction.task_id != task_id
            or transaction.state != TransactionState.PREPARED
            or transaction.manifest_artifact_ref is None
        ):
            raise CreateFileError("prepared transaction required")
        return transaction


def _normalize_relative_path(relative_path: str) -> str:
    try:
        return canonical_project_path(relative_path)
    except ProjectPathError as exc:
        raise CreateFileError("target path invalid") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
