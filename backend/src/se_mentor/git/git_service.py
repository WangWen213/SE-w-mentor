from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitStatus:
    modified: tuple[str, ...]
    untracked: tuple[str, ...]


@dataclass(frozen=True)
class GitTaskSnapshot:
    base_revision: str
    preexisting_changes: tuple[str, ...]
    file_hashes: dict[str, str]


@dataclass(frozen=True)
class GitChangeDetection:
    agent_changes: tuple[str, ...]
    external_changes: tuple[str, ...]
    preexisting_changes: tuple[str, ...]


class GitService:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()
        self._agent_written: set[str] = set()

    def base_revision(self) -> str:
        return self._git("rev-parse", "HEAD")

    def status(self) -> GitStatus:
        entries = (
            self._git_bytes("status", "--porcelain=v1", "-z")
            .decode("utf-8", errors="ignore")
            .split("\0")
        )
        modified: list[str] = []
        untracked: list[str] = []
        for entry in entries:
            if not entry:
                continue
            code = entry[:2]
            path = entry[3:]
            if code == "??":
                untracked.append(path)
            else:
                modified.append(path)
        return GitStatus(tuple(sorted(modified)), tuple(sorted(untracked)))

    def capture_task_baseline(self) -> GitTaskSnapshot:
        status = self.status()
        paths = tuple(sorted((*status.modified, *status.untracked)))
        return GitTaskSnapshot(
            self.base_revision(), paths, {path: self._hash(path) for path in paths}
        )

    def record_agent_write(self, relative_path: str) -> None:
        self._agent_written.add(Path(relative_path).as_posix())

    def detect_external_modifications(self, snapshot: GitTaskSnapshot) -> GitChangeDetection:
        current_status = self.status()
        current = set(current_status.modified) | set(current_status.untracked)
        agent = tuple(sorted(current.intersection(self._agent_written)))
        external = tuple(
            sorted(
                path
                for path in current
                if path not in self._agent_written
                and (
                    path not in snapshot.file_hashes
                    or self._hash(path) != snapshot.file_hashes[path]
                )
            )
        )
        return GitChangeDetection(agent, external, snapshot.preexisting_changes)

    def scoped_diff(self, relative_paths: list[str]) -> str:
        return self._git("diff", "--", *relative_paths)

    def file_history(self, relative_path: str, *, max_entries: int = 5) -> tuple[str, ...]:
        output = self._git(
            "log", f"--max-count={max_entries}", "--format=%H %s", "--", relative_path
        )
        return tuple(line for line in output.splitlines() if line)

    def _hash(self, relative_path: str) -> str:
        path = self.root / relative_path
        if not path.exists():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _git(self, *args: str) -> str:
        return self._git_bytes(*args).decode("utf-8", errors="ignore").strip()

    def _git_bytes(self, *args: str) -> bytes:
        result = subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        return result.stdout
