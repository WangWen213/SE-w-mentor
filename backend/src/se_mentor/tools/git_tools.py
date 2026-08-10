from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from se_mentor.git.git_service import GitService, GitTaskSnapshot
from se_mentor.tools.registry import ToolRegistry, ToolSpec

_READ_ONLY_GIT_TOOL_SPECS = (
    ToolSpec("git_status", "read", 10),
    ToolSpec("git_revision", "read", 10),
    ToolSpec("git_diff", "read", 10),
    ToolSpec("git_history", "read", 10),
    ToolSpec("git_external_changes", "read", 10),
)


class GitToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitStatusSummary:
    modified: tuple[str, ...]
    untracked: tuple[str, ...]
    porcelain: str


@dataclass(frozen=True)
class GitRevisionSummary:
    head: str


@dataclass(frozen=True)
class GitDiffSummary:
    text: str
    line_count: int
    truncated: bool


@dataclass(frozen=True)
class GitHistorySummary:
    entries: tuple[str, ...]


@dataclass(frozen=True)
class GitExternalChangesSummary:
    agent_changes: tuple[str, ...]
    external_changes: tuple[str, ...]
    preexisting_changes: tuple[str, ...]


class ReadOnlyGitTools:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()
        self.git = GitService(self.root)

    def status(self, *, pathspec: tuple[str, ...] = ()) -> GitStatusSummary:
        normalized = self._validate_pathspecs(pathspec)
        porcelain = self._git("status", "--porcelain=v1", "--", *normalized)
        status = self.git.status()
        if not normalized:
            return GitStatusSummary(status.modified, status.untracked, porcelain)
        selected = set(normalized)
        return GitStatusSummary(
            tuple(path for path in status.modified if path in selected),
            tuple(path for path in status.untracked if path in selected),
            porcelain,
        )

    def revision(self) -> GitRevisionSummary:
        return GitRevisionSummary(self.git.base_revision())

    def diff(
        self,
        *,
        pathspec: tuple[str, ...] = (),
        max_lines: int = 200,
    ) -> GitDiffSummary:
        normalized = self._validate_pathspecs(pathspec)
        text = self._git("diff", "--", *normalized)
        lines = text.splitlines(keepends=True)
        truncated = len(lines) > max_lines
        if truncated:
            text = "".join(lines[:max_lines])
        return GitDiffSummary(text, len(lines), truncated)

    def history(self, relative_path: str, *, max_entries: int = 5) -> GitHistorySummary:
        normalized = self._validate_pathspecs((relative_path,))
        return GitHistorySummary(self.git.file_history(normalized[0], max_entries=max_entries))

    def external_changes(self, snapshot: GitTaskSnapshot) -> GitExternalChangesSummary:
        changes = self.git.detect_external_modifications(snapshot)
        return GitExternalChangesSummary(
            changes.agent_changes,
            changes.external_changes,
            changes.preexisting_changes,
        )

    def _validate_pathspecs(self, pathspec: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in pathspec:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                raise GitToolError("pathspec outside project")
            resolved = (self.root / path).resolve()
            if not resolved.is_relative_to(self.root):
                raise GitToolError("pathspec outside project")
            normalized.append(path.as_posix())
        return tuple(normalized)

    def _git(self, *args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise GitToolError(exc.stderr.strip() or "git command failed") from exc


def register_read_only_git_tools(registry: ToolRegistry) -> None:
    for spec in _READ_ONLY_GIT_TOOL_SPECS:
        registry.register(spec)
