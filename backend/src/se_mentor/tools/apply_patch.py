from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

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

LOGGER = logging.getLogger("se_mentor.tools.apply_patch")


class ApplyPatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class StructuredPatch:
    relative_path: str
    expected_sha256: str
    replacements: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ApplyPatchResult:
    relative_path: str
    before_sha256: str
    after_sha256: str
    diff: str
    tool_execution_id: str


class AtomicApplyPatchTool:
    def __init__(self, session: Session, *, project_root: str | Path) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()

    def apply(
        self,
        *,
        task_id: str,
        action_id: str,
        transaction_id: str,
        grant: TemporaryGrant | ExecutionAuthorization,
        patch: StructuredPatch,
        revision: str,
        pre_replace_hook: Callable[[], None] | None = None,
        simulate_crash_before_replace: bool = False,
    ) -> ApplyPatchResult:
        total_started = perf_counter()
        prepare_started = perf_counter()
        transaction = self._prepared_transaction(transaction_id, task_id)
        relative_path = _normalize_relative_path(patch.relative_path)
        if not grant.allows_write(relative_path, revision=revision):
            raise ApplyPatchError("policy scope denied")
        target = (self.project_root / relative_path).resolve()
        if not target.is_relative_to(self.project_root) or not target.is_file():
            raise ApplyPatchError("target path invalid")
        LOGGER.info(
            (
                "[perf] tool.apply_patch.prepare task_id=%s project_id=%s "
                "duration_ms=%s patch_operations=%s patch_chars=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - prepare_started) * 1000),
            len(patch.replacements),
            sum(len(old) + len(new) for old, new in patch.replacements),
        )

        file_read_started = perf_counter()
        before_bytes = target.read_bytes()
        before_hash = _sha(before_bytes)
        if before_hash != patch.expected_sha256:
            raise ApplyPatchError("expected hash conflict")
        try:
            before_text = before_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApplyPatchError("encoding error") from exc
        LOGGER.info(
            (
                "[perf] tool.apply_patch.file_read task_id=%s project_id=%s "
                "duration_ms=%s files_count=%s bytes_read=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - file_read_started) * 1000),
            1,
            len(before_bytes),
        )

        apply_started = perf_counter()
        after_text = _apply_replacements(before_text, patch.replacements)
        LOGGER.info(
            (
                "[perf] tool.apply_patch.apply task_id=%s project_id=%s "
                "duration_ms=%s patch_operations=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - apply_started) * 1000),
            len(patch.replacements),
        )

        diff_started = perf_counter()
        diff = _diff(relative_path, before_text, after_text)
        LOGGER.info(
            "[perf] tool.apply_patch.diff task_id=%s project_id=%s duration_ms=%s diff_chars=%s",
            task_id,
            transaction.project_id,
            int((perf_counter() - diff_started) * 1000),
            len(diff),
        )

        backup_started = perf_counter()
        backup_path, backup_bytes = _backup_file(transaction, target, relative_path)
        LOGGER.info(
            (
                "[perf] tool.apply_patch.backup task_id=%s project_id=%s "
                "duration_ms=%s backup_files=%s backup_bytes=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - backup_started) * 1000),
            1,
            backup_bytes,
        )

        file_write_started = perf_counter()
        temp_path = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        temp_path.write_text(after_text, encoding="utf-8", newline="")
        temp_path.read_text(encoding="utf-8")
        bytes_written = len(after_text.encode("utf-8"))
        LOGGER.info(
            (
                "[perf] tool.apply_patch.temp_write task_id=%s project_id=%s "
                "duration_ms=%s files_written=%s bytes_written=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - file_write_started) * 1000),
            1,
            bytes_written,
        )

        if pre_replace_hook is not None:
            pre_replace_hook()
        replace_started = perf_counter()
        if _sha(target.read_bytes()) != before_hash:
            temp_path.unlink(missing_ok=True)
            raise ApplyPatchError("external modification before replace")
        if simulate_crash_before_replace:
            temp_path.unlink(missing_ok=True)
            raise ApplyPatchError("pre_replace_crash")

        os.replace(temp_path, target)
        after_hash = _sha(target.read_bytes())
        LOGGER.info(
            (
                "[perf] tool.apply_patch.replace task_id=%s project_id=%s "
                "duration_ms=%s files_written=%s bytes_written=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - replace_started) * 1000),
            1,
            bytes_written,
        )

        persist_started = perf_counter()
        tool_execution = ToolExecution(
            task_id=task_id,
            action_id=action_id,
            transaction_id=transaction.id,
            tool_name="APPLY_PATCH",
            command_summary=f"apply patch {relative_path}",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps({"relative_path": relative_path, "diff": diff}),
        )
        self.session.add(tool_execution)
        self.session.flush()
        backup = BackupEntry(
            task_id=task_id,
            project_id=transaction.project_id,
            original_hash=before_hash,
            backup_artifact_ref=str(backup_path),
            file_type="text/plain",
            relative_path=relative_path,
        )
        self.session.add(backup)
        self.session.flush()
        self.session.add(
            FileChange(
                task_id=task_id,
                tool_execution_id=tool_execution.id,
                action_id=action_id,
                backup_entry_id=backup.id,
                change_type=FileChangeType.MODIFY,
                relative_path=relative_path,
                before_hash=before_hash,
                after_hash=after_hash,
            )
        )
        self.session.flush()
        LOGGER.info(
            "[perf] tool.apply_patch.persist task_id=%s project_id=%s duration_ms=%s",
            task_id,
            transaction.project_id,
            int((perf_counter() - persist_started) * 1000),
        )
        LOGGER.info(
            (
                "[perf] tool.apply_patch.inner_total task_id=%s project_id=%s "
                "duration_ms=%s patch_operations=%s files_read=%s files_written=%s "
                "bytes_read=%s bytes_written=%s diff_chars=%s"
            ),
            task_id,
            transaction.project_id,
            int((perf_counter() - total_started) * 1000),
            len(patch.replacements),
            1,
            1,
            len(before_bytes),
            bytes_written,
            len(diff),
        )
        return ApplyPatchResult(relative_path, before_hash, after_hash, diff, tool_execution.id)

    def _prepared_transaction(self, transaction_id: str, task_id: str) -> TaskTransaction:
        transaction = self.session.get(TaskTransaction, transaction_id)
        if (
            transaction is None
            or transaction.task_id != task_id
            or transaction.state != TransactionState.PREPARED
            or transaction.manifest_artifact_ref is None
        ):
            raise ApplyPatchError("prepared transaction required")
        return transaction


def _normalize_relative_path(relative_path: str) -> str:
    try:
        return canonical_project_path(relative_path)
    except ProjectPathError as exc:
        raise ApplyPatchError("target path invalid") from exc


def _apply_replacements(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    result = text
    for old, new in replacements:
        if old not in result:
            raise ApplyPatchError("patch mismatch")
        result = result.replace(old, new, 1)
    return result


def _backup_file(
    transaction: TaskTransaction, target: Path, relative_path: str
) -> tuple[Path, int]:
    manifest_path = Path(str(transaction.manifest_artifact_ref))
    backup_dir = manifest_path.parent / "files" / relative_path
    backup_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_bytes = target.read_bytes()
    backup_dir.write_bytes(backup_bytes)
    return backup_dir, len(backup_bytes)


def _diff(relative_path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
