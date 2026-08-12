from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from se_mentor.security.path_policy import PathPolicy

_EXCLUDED_DIRS = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".sementor",
    ".tmp",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "evidence",
    "node_modules",
}


@dataclass(frozen=True)
class FileInventoryEntry:
    relative_path: str
    size: int
    mtime: float
    sha256: str
    git_status: str


@dataclass(frozen=True)
class ExcludedFileEntry:
    relative_path: str
    reason: str


@dataclass(frozen=True)
class FileInventory:
    files: tuple[FileInventoryEntry, ...]
    excluded: tuple[ExcludedFileEntry, ...]
    limit_status: str = "OK"
    total_size: int = 0
    evidence: tuple[str, ...] = field(default_factory=tuple)


def build_file_inventory(
    project_root: str | Path,
    *,
    max_file_size_bytes: int = 1_000_000,
    max_files: int = 10_000,
    max_total_size_bytes: int = 50_000_000,
) -> FileInventory:
    root = Path(project_root).resolve()
    policy = PathPolicy(root, max_file_size_bytes=max_file_size_bytes)
    git_status = _git_status(root)
    files: list[FileInventoryEntry] = []
    excluded: list[ExcludedFileEntry] = []
    total_size = 0
    scanned = 0
    limit_status = "OK"

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        scanned += 1
        if scanned > max_files:
            limit_status = "FILE_COUNT_LIMIT"
            break
        if _is_git_ignored(root, rel):
            excluded.append(ExcludedFileEntry(rel, "GIT_IGNORED"))
            continue
        decision = policy.resolve(rel)
        if not decision.allowed:
            excluded.append(ExcludedFileEntry(rel, decision.reason))
            continue
        assert decision.path is not None
        if policy.is_binary(decision.path):
            excluded.append(ExcludedFileEntry(rel, "BINARY_FILE"))
            continue
        size = decision.path.stat().st_size
        if total_size + size > max_total_size_bytes:
            limit_status = "TOTAL_SIZE_LIMIT"
            break
        total_size += size
        files.append(
            FileInventoryEntry(
                relative_path=rel,
                size=size,
                mtime=decision.path.stat().st_mtime,
                sha256=hashlib.sha256(decision.path.read_bytes()).hexdigest(),
                git_status=git_status.get(rel, "CLEAN"),
            )
        )
    return FileInventory(tuple(files), tuple(excluded), limit_status, total_size)


def _git_status(root: Path) -> dict[str, str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
        text=False,
        timeout=10,
    )
    if result.returncode != 0:
        return {}
    entries = [item for item in result.stdout.decode("utf-8", errors="ignore").split("\0") if item]
    statuses: dict[str, str] = {}
    for entry in entries:
        code = entry[:2]
        path = entry[3:]
        statuses[path] = "UNTRACKED" if code == "??" else "MODIFIED"
    return statuses


def _is_git_ignored(root: Path, relative_path: str) -> bool:
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if toplevel.returncode != 0 or Path(toplevel.stdout.strip()).resolve() != root:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", relative_path],
        cwd=root,
        check=False,
        timeout=10,
    )
    return result.returncode == 0


def _iter_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in _EXCLUDED_DIRS]
        current_path = Path(current)
        for name in sorted(files):
            yield current_path / name
