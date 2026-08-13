from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.execution import (
    TaskTransaction,
    TransactionState,
    WorkspaceLock,
    WorkspaceLockMode,
    WorkspaceLockStatus,
)
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask

LOGGER = logging.getLogger("se_mentor.transactions.manager")


class TransactionPrepareError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedTransaction:
    transaction_id: str
    state: str
    manifest_path: Path
    backup_dir: Path
    file_hashes: dict[str, str]


class TransactionManager:
    def __init__(self, session: Session, *, backup_root: str | Path | None = None) -> None:
        self.session = session
        self.backup_root = Path(backup_root) if backup_root is not None else None

    def prepare(
        self,
        *,
        task_id: str,
        project_id: str,
        lock_id: str,
        expected_base_revision: str,
    ) -> PreparedTransaction:
        total_started = perf_counter()
        lookup_started = perf_counter()
        task = self.session.get(ChangeTask, task_id)
        project = self.session.get(Project, project_id)
        if task is None or project is None or task.project_id != project_id:
            raise TransactionPrepareError("task/project mismatch")
        lock = self._active_write_lock(lock_id, task_id, project_id)
        if task.base_revision != expected_base_revision:
            raise TransactionPrepareError("baseRevision mismatch")
        LOGGER.info(
            "[perf] tool.apply_patch.transaction.lookup task_id=%s project_id=%s duration_ms=%s",
            task_id,
            project_id,
            int((perf_counter() - lookup_started) * 1000),
        )

        existing_started = perf_counter()
        existing = self.session.scalar(
            select(TaskTransaction).where(
                TaskTransaction.task_id == task_id,
                TaskTransaction.project_id == project_id,
                TaskTransaction.workspace_lock_id == lock.id,
                TaskTransaction.state == TransactionState.PREPARED,
            )
        )
        if existing is not None and existing.manifest_artifact_ref is not None:
            prepared = self._from_existing(existing, project)
            LOGGER.info(
                (
                    "[perf] tool.apply_patch.transaction.existing task_id=%s project_id=%s "
                    "duration_ms=%s manifest_files=%s"
                ),
                task_id,
                project_id,
                int((perf_counter() - existing_started) * 1000),
                len(prepared.file_hashes),
            )
            LOGGER.info(
                (
                    "[perf] tool.apply_patch.transaction.prepare task_id=%s project_id=%s "
                    "duration_ms=%s mode=existing manifest_files=%s"
                ),
                task_id,
                project_id,
                int((perf_counter() - total_started) * 1000),
                len(prepared.file_hashes),
            )
            return prepared

        project_root = Path(project.root_path).resolve()
        backup_dir = self._backup_dir(project_root, task_id)
        if backup_dir.resolve().is_relative_to(project_root):
            raise TransactionPrepareError("backup directory cannot be inside repository")
        manifest_started = perf_counter()
        file_hashes, manifest_scanned, manifest_skipped, manifest_bytes = _workspace_hashes(
            project_root
        )
        LOGGER.info(
            (
                "[perf] tool.apply_patch.transaction_manifest task_id=%s project_id=%s "
                "duration_ms=%s manifest_files=%s scanned_files=%s skipped_files=%s bytes_read=%s"
            ),
            task_id,
            project_id,
            int((perf_counter() - manifest_started) * 1000),
            len(file_hashes),
            manifest_scanned,
            manifest_skipped,
            manifest_bytes,
        )
        manifest = {
            "task_id": task_id,
            "project_id": project_id,
            "lock_id": lock.id,
            "base_revision": expected_base_revision,
            "workspace_state": "DIRTY" if file_hashes else "CLEAN",
            "preexisting_changes": [
                {"path": path, "sha256": file_hashes[path]} for path in sorted(file_hashes)
            ],
            "backup_dir": str(backup_dir),
        }

        artifact_started = perf_counter()
        backup_dir.mkdir(parents=True, exist_ok=True)
        _restrict_directory(backup_dir)
        manifest_path = backup_dir / "baseline-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        _restrict_file(manifest_path)
        LOGGER.info(
            (
                "[perf] tool.apply_patch.transaction_artifacts task_id=%s project_id=%s "
                "duration_ms=%s manifest_files=%s"
            ),
            task_id,
            project_id,
            int((perf_counter() - artifact_started) * 1000),
            len(file_hashes),
        )
        persist_started = perf_counter()
        transaction = TaskTransaction(
            task_id=task_id,
            project_id=project_id,
            workspace_lock_id=lock.id,
            state=TransactionState.PREPARED,
            manifest_artifact_ref=str(manifest_path),
        )
        self.session.add(transaction)
        self.session.flush()
        LOGGER.info(
            "[perf] tool.apply_patch.transaction_persist task_id=%s project_id=%s duration_ms=%s",
            task_id,
            project_id,
            int((perf_counter() - persist_started) * 1000),
        )
        LOGGER.info(
            (
                "[perf] tool.apply_patch.transaction.prepare task_id=%s project_id=%s "
                "duration_ms=%s mode=new manifest_files=%s scanned_files=%s skipped_files=%s "
                "bytes_read=%s"
            ),
            task_id,
            project_id,
            int((perf_counter() - total_started) * 1000),
            len(file_hashes),
            manifest_scanned,
            manifest_skipped,
            manifest_bytes,
        )
        return PreparedTransaction(
            transaction.id,
            transaction.state,
            manifest_path,
            backup_dir,
            file_hashes,
        )

    def _active_write_lock(
        self,
        lock_id: str,
        task_id: str,
        project_id: str,
    ) -> WorkspaceLock:
        lock = self.session.get(WorkspaceLock, lock_id)
        now = datetime.now(UTC)
        if (
            lock is None
            or lock.task_id != task_id
            or lock.project_id != project_id
            or lock.lock_mode != WorkspaceLockMode.WRITE
            or lock.status != WorkspaceLockStatus.ACTIVE
            or (lock.expires_at is not None and _as_aware(lock.expires_at) <= now)
        ):
            raise TransactionPrepareError("active WRITE lock required")
        return lock

    def _backup_dir(self, project_root: Path, task_id: str) -> Path:
        root = (
            self.backup_root if self.backup_root is not None else project_root.parent / ".sementor"
        )
        return (root / "backups" / task_id).resolve()

    def _from_existing(self, transaction: TaskTransaction, project: Project) -> PreparedTransaction:
        manifest_path = Path(str(transaction.manifest_artifact_ref))
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        file_hashes = {
            str(item["path"]): str(item["sha256"])
            for item in data.get("preexisting_changes", [])
            if isinstance(item, dict)
        }
        return PreparedTransaction(
            transaction.id,
            transaction.state,
            manifest_path,
            Path(str(data["backup_dir"])),
            file_hashes or _workspace_hashes(Path(project.root_path).resolve())[0],
        )


def _workspace_hashes(project_root: Path) -> tuple[dict[str, str], int, int, int]:
    if not project_root.exists():
        return {}, 0, 0, 0
    hashes: dict[str, str] = {}
    scanned_files = 0
    skipped_files = 0
    bytes_read = 0
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            skipped_files += 1
            continue
        relative = path.relative_to(project_root).as_posix()
        content = path.read_bytes()
        scanned_files += 1
        bytes_read += len(content)
        hashes[relative] = hashlib.sha256(content).hexdigest()
    return hashes, scanned_files, skipped_files, bytes_read


def _restrict_directory(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:
        return


def _restrict_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
