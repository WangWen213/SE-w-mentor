from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".npmrc", ".pypirc"}
SENSITIVE_FRAGMENTS = ("secret", "token", "password", "credential")
BACKUP_SUFFIXES = ("~", ".bak", ".backup", ".orig", ".swp")


@dataclass(frozen=True)
class PathDecision:
    allowed: bool
    reason: str
    path: Path | None = None
    relative_path: str | None = None


class PathPolicy:
    def __init__(self, project_root: str | Path, *, max_file_size_bytes: int = 1_000_000) -> None:
        self.project_root = Path(project_root).resolve()
        self.max_file_size_bytes = max_file_size_bytes

    def resolve(self, relative_path: str | Path) -> PathDecision:
        candidate = Path(relative_path)
        path = candidate if candidate.is_absolute() else self.project_root / candidate
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            return PathDecision(False, "NOT_FOUND")
        try:
            rel = resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return PathDecision(False, "REALPATH_OUTSIDE_PROJECT", resolved)
        if _is_sensitive(rel):
            return PathDecision(False, "SENSITIVE_FILE", resolved, rel)
        if any(rel.endswith(suffix) for suffix in BACKUP_SUFFIXES):
            return PathDecision(False, "BACKUP_FILE", resolved, rel)
        if resolved.is_file() and resolved.stat().st_size > self.max_file_size_bytes:
            return PathDecision(False, "FILE_TOO_LARGE", resolved, rel)
        return PathDecision(True, "OK", resolved, rel)

    def is_binary(self, path: Path) -> bool:
        sample = path.read_bytes()[:4096]
        return b"\x00" in sample


def _is_sensitive(relative_path: str) -> bool:
    name = Path(relative_path).name.lower()
    lowered = relative_path.lower()
    return name in SENSITIVE_NAMES or any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)
