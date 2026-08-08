from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from se_mentor.indexing.file_inventory import build_file_inventory
from se_mentor.security.path_policy import PathPolicy


@dataclass(frozen=True)
class EvidenceRef:
    relative_path: str
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class DirectoryEntry:
    relative_path: str
    kind: str


@dataclass(frozen=True)
class DirectoryListing:
    status: str
    entries: tuple[DirectoryEntry, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class FileLine:
    line_number: int
    text: str


@dataclass(frozen=True)
class ReadFileResult:
    status: str
    content: str
    lines: tuple[FileLine, ...]
    evidence: EvidenceRef
    truncated: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class SearchHit:
    relative_path: str
    line_number: int
    line: str
    evidence_ref: EvidenceRef


@dataclass(frozen=True)
class SearchResult:
    status: str
    hits: tuple[SearchHit, ...]
    truncated: bool


class RepositoryReader:
    def __init__(
        self,
        project_root: str | Path,
        *,
        max_read_bytes: int = 64_000,
        max_search_results: int = 50,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.max_read_bytes = max_read_bytes
        self.max_search_results = max_search_results
        self.policy = PathPolicy(self.root)

    def list_directory(self, relative_path: str = ".") -> DirectoryListing:
        decision = self.policy.resolve(relative_path)
        if not decision.allowed:
            return DirectoryListing("REJECTED", reason=decision.reason)
        assert decision.path is not None
        if not decision.path.is_dir():
            return DirectoryListing("REJECTED", reason="NOT_DIRECTORY")
        entries = []
        for path in sorted(decision.path.iterdir(), key=lambda value: value.name):
            rel = path.resolve().relative_to(self.root).as_posix()
            child = self.policy.resolve(rel)
            if child.allowed:
                entries.append(DirectoryEntry(rel, "directory" if path.is_dir() else "file"))
        return DirectoryListing("OK", tuple(entries))

    def read_file(self, relative_path: str) -> ReadFileResult:
        decision = self.policy.resolve(relative_path)
        evidence = EvidenceRef(decision.relative_path or relative_path)
        if not decision.allowed:
            return ReadFileResult("REJECTED", "", (), evidence, reason=decision.reason)
        assert decision.path is not None and decision.relative_path is not None
        if self.policy.is_binary(decision.path):
            return ReadFileResult(
                "BINARY", "", (), EvidenceRef(decision.relative_path), reason="BINARY_FILE"
            )
        data = decision.path.read_bytes()
        truncated = len(data) > self.max_read_bytes
        content = data[: self.max_read_bytes].decode("utf-8", errors="replace")
        lines = tuple(
            FileLine(index, line) for index, line in enumerate(content.splitlines(), start=1)
        )
        return ReadFileResult("OK", content, lines, EvidenceRef(decision.relative_path), truncated)

    def search_code(self, query: str) -> SearchResult:
        hits: list[SearchHit] = []
        truncated = False
        inventory = build_file_inventory(self.root)
        for entry in inventory.files:
            decision = self.policy.resolve(entry.relative_path)
            if not decision.allowed or decision.path is None:
                continue
            for index, text in enumerate(
                decision.path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if query in text:
                    if len(hits) >= self.max_search_results:
                        truncated = True
                        return SearchResult("OK", tuple(hits), truncated)
                    hits.append(
                        SearchHit(
                            entry.relative_path,
                            index,
                            text,
                            EvidenceRef(entry.relative_path, index, index),
                        )
                    )
        return SearchResult("OK", tuple(hits), truncated)
