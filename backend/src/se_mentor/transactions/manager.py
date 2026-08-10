from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
        task = self.session.get(ChangeTask, task_id)
        project = self.session.get(Project, project_id)
        if task is None or project is None or task.project_id != project_id:
            raise TransactionPrepareError("task/project mismatch")
        lock = self._active_write_lock(lock_id, task_id, project_id)
        if task.base_revision != expected_base_revision:
            raise TransactionPrepareError("baseRevision mismatch")

        existing = self.session.scalar(
            select(TaskTransaction).where(
                TaskTransaction.task_id == task_id,
                TaskTransaction.project_id == project_id,
                TaskTransaction.workspace_lock_id == lock.id,
                TaskTransaction.state == TransactionState.PREPARED,
            )
        )
        if existing is not None and existing.manifest_artifact_ref is not None:
            return self._from_existing(existing, project)

        project_root = Path(project.root_path).resolve()
        backup_dir = self._backup_dir(project_root, task_id)
        if backup_dir.resolve().is_relative_to(project_root):
            raise TransactionPrepareError("backup directory cannot be inside repository")
        file_hashes = _workspace_hashes(project_root)
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

        backup_dir.mkdir(parents=True, exist_ok=True)
        _restrict_directory(backup_dir)
        manifest_path = backup_dir / "baseline-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        _restrict_file(manifest_path)
        transaction = TaskTransaction(
            task_id=task_id,
            project_id=project_id,
            workspace_lock_id=lock.id,
            state=TransactionState.PREPARED,
            manifest_artifact_ref=str(manifest_path),
        )
        self.session.add(transaction)
        self.session.flush()
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
            file_hashes or _workspace_hashes(Path(project.root_path).resolve()),
        )


def _workspace_hashes(project_root: Path) -> dict[str, str]:
    if not project_root.exists():
        return {}
    hashes: dict[str, str] = {}
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(project_root).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


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
