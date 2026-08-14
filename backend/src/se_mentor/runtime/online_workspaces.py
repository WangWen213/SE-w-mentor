from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from se_mentor.runtime.online_sessions import OnlineSession

ONLINE_SAFE_USER_PATH_ERROR = "ONLINE_SAFE_USER_PATH_NOT_ALLOWED"
ONLINE_SAFE_WORKSPACE_LIMIT_ERROR = "ONLINE_SAFE_WORKSPACE_LIMIT_EXCEEDED"
ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR = "ONLINE_SAFE_WORKSPACE_BOUNDARY_VIOLATION"
ONLINE_SAFE_WORKSPACE_BASELINE_ERROR = "ONLINE_SAFE_WORKSPACE_BASELINE_INVALID"
ONLINE_SAFE_WORKSPACE_MAX_BYTES = 100 * 1024 * 1024
ONLINE_SAFE_WORKSPACE_MAX_FILES = 5000
ONLINE_SAFE_WORKSPACE_BASELINE_NAME = "demo-baseline"

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,}$")
_EXCLUDED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
_EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.test",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "se_mentor_api.sqlite3",
    "se_mentor_api.sqlite3-shm",
    "se_mentor_api.sqlite3-wal",
}
_EXCLUDED_SUFFIXES = (".log", ".key", ".pem")


class OnlineWorkspaceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class WorkspaceHandle:
    session_id: str
    root: Path
    created_at: datetime
    last_used_at: datetime
    baseline_name: str
    baseline_revision: str | None = None

    @property
    def identifier(self) -> str:
        return hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()[:16]


class SafeOnlineWorkspaceFactory:
    def __init__(
        self,
        *,
        runtime_root: str | Path,
        baseline_root: str | Path,
        baseline_name: str = ONLINE_SAFE_WORKSPACE_BASELINE_NAME,
        max_bytes: int = ONLINE_SAFE_WORKSPACE_MAX_BYTES,
        max_files: int = ONLINE_SAFE_WORKSPACE_MAX_FILES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_files <= 0:
            raise ValueError("max_files must be positive")
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.sessions_root = (self.runtime_root / "sessions").resolve()
        self.baseline_root = Path(baseline_root).expanduser().resolve()
        self.baseline_name = baseline_name
        self.max_bytes = max_bytes
        self.max_files = max_files
        self._clock = clock or (lambda: datetime.now(UTC))
        self._handles: dict[str, WorkspaceHandle] = {}

    def get_or_create(self, session: OnlineSession) -> WorkspaceHandle:
        now = self._clock()
        session_root = self._session_root(session.session_id)
        workspace_root = (session_root / "workspace").resolve()
        if session.session_id in self._handles and workspace_root.is_dir():
            handle = self._handles[session.session_id]
            handle.last_used_at = now
            return handle
        self._ensure_inside(workspace_root, session_root)
        if not workspace_root.is_dir():
            try:
                session_root.mkdir(parents=True, exist_ok=True)
                self._copy_baseline(workspace_root)
                self._init_session_git_repo(workspace_root)
            except Exception:
                self._safe_rmtree(session_root)
                raise
        handle = WorkspaceHandle(
            session_id=session.session_id,
            root=workspace_root,
            created_at=now,
            last_used_at=now,
            baseline_name=self.baseline_name,
            baseline_revision=self._baseline_revision(),
        )
        self._handles[session.session_id] = handle
        return handle

    def reset_current_workspace(self, session: OnlineSession) -> WorkspaceHandle:
        session_root = self._session_root(session.session_id)
        workspace_root = (session_root / "workspace").resolve()
        if workspace_root.exists():
            self._safe_rmtree(workspace_root)
        self._handles.pop(session.session_id, None)
        return self.get_or_create(session)

    def cleanup_expired(self, active_session_ids: Collection[str]) -> None:
        active = set(active_session_ids)
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        for child in self.sessions_root.iterdir():
            if child.name in active:
                continue
            self._safe_rmtree(child)
            self._handles.pop(child.name, None)

    def resolve_workspace_path(self, handle: WorkspaceHandle, relative_path: str) -> Path:
        requested = Path(relative_path)
        if requested.is_absolute() or ".." in requested.parts:
            raise OnlineWorkspaceError(
                ONLINE_SAFE_USER_PATH_ERROR,
                "ONLINE_SAFE workspace paths must be relative to the session workspace",
            )
        target = (handle.root / requested).resolve()
        self._ensure_inside(target, handle.root)
        return target

    def _copy_baseline(self, destination: Path) -> None:
        if not self.baseline_root.is_dir():
            raise OnlineWorkspaceError(
                ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
                "ONLINE_SAFE baseline workspace is missing",
            )
        self._validate_baseline()
        destination.mkdir(parents=True, exist_ok=False)
        files = 0
        total_bytes = 0
        for source in self.baseline_root.rglob("*"):
            relative = source.relative_to(self.baseline_root)
            if source.is_symlink():
                raise OnlineWorkspaceError(
                    ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
                    "ONLINE_SAFE baseline symlinks are not allowed",
                )
            if self._is_excluded(relative):
                continue
            target = destination / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not source.is_file():
                raise OnlineWorkspaceError(
                    ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
                    "ONLINE_SAFE baseline contains unsupported filesystem entries",
                )
            files += 1
            total_bytes += source.stat().st_size
            if files > self.max_files or total_bytes > self.max_bytes:
                raise OnlineWorkspaceError(
                    ONLINE_SAFE_WORKSPACE_LIMIT_ERROR,
                    "ONLINE_SAFE baseline workspace exceeds configured limits",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)

    def _validate_baseline(self) -> None:
        files = 0
        total_bytes = 0
        for source in self.baseline_root.rglob("*"):
            relative = source.relative_to(self.baseline_root)
            if source.is_symlink():
                raise OnlineWorkspaceError(
                    ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
                    "ONLINE_SAFE baseline symlinks are not allowed",
                )
            if self._is_excluded(relative):
                continue
            if source.is_file():
                files += 1
                total_bytes += source.stat().st_size
                if files > self.max_files or total_bytes > self.max_bytes:
                    raise OnlineWorkspaceError(
                        ONLINE_SAFE_WORKSPACE_LIMIT_ERROR,
                        "ONLINE_SAFE baseline workspace exceeds configured limits",
                    )

    def _init_session_git_repo(self, workspace_root: Path) -> None:
        commands = (
            ["git", "init"],
            ["git", "config", "user.email", "online-safe@example.invalid"],
            ["git", "config", "user.name", "SE-Mentor Online Safe"],
            ["git", "config", "--unset-all", "credential.helper"],
            ["git", "add", "."],
            ["git", "commit", "-m", "baseline"],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=workspace_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                continue
            if command[:3] == ["git", "config", "--unset-all"] and completed.returncode == 5:
                continue
            raise OnlineWorkspaceError(
                ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
                "ONLINE_SAFE session Git baseline could not be initialized",
            )

    def _baseline_revision(self) -> str:
        digest = hashlib.sha256()
        for source in sorted(self.baseline_root.rglob("*")):
            relative = source.relative_to(self.baseline_root)
            if self._is_excluded(relative) or not source.is_file():
                continue
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(source.read_bytes())
        return digest.hexdigest()[:16]

    def _safe_rmtree(self, target: Path) -> None:
        resolved = Path(target).resolve()
        self._ensure_inside(resolved, self.sessions_root)
        if resolved == self.sessions_root:
            raise OnlineWorkspaceError(
                ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR,
                "ONLINE_SAFE cleanup target cannot be the sessions root",
            )
        if resolved.exists():
            shutil.rmtree(resolved, onexc=_remove_readonly)

    def _session_root(self, session_id: str) -> Path:
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise OnlineWorkspaceError(
                ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR,
                "ONLINE_SAFE session id is not a valid workspace identifier",
            )
        session_root = (self.sessions_root / session_id).resolve()
        self._ensure_inside(session_root, self.sessions_root)
        return session_root

    @staticmethod
    def _is_excluded(relative: Path) -> bool:
        parts = set(relative.parts)
        name = relative.name
        return (
            bool(parts & _EXCLUDED_NAMES)
            or name in _EXCLUDED_FILES
            or name.startswith(".env.")
            or name.endswith(_EXCLUDED_SUFFIXES)
        )

    @staticmethod
    def _ensure_inside(target: Path, root: Path) -> None:
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise OnlineWorkspaceError(
                ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR,
                "ONLINE_SAFE workspace path escaped its boundary",
            ) from exc


def _remove_readonly(function: Callable[[str], None], path: str, exc: BaseException) -> None:
    if not isinstance(exc, PermissionError):
        raise exc
    os.chmod(path, stat.S_IWRITE)
    function(path)
