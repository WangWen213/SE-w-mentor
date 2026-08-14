from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.context.context_builder import (
    ContextBuilder,
    ContextItem,
    ContextPackage,
    TrustLabel,
)
from se_mentor.git.git_service import GitService
from se_mentor.knowledge.retrieval import KnowledgeRetriever
from se_mentor.models.code_index import CodeSymbol
from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeSource
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeProposal, ChangeTask

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
_EXCLUDED_CONTEXT_PREFIXES = ("backend/migrations/",)
_MIGRATION_KEYWORDS = (
    "database",
    "schema",
    "migration",
    "migrate",
    "sql",
    "table",
    "model",
    "persistence",
)
_FRONTEND_TEXT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")
_LIGHTWEIGHT_TEXT_DIRS = (
    Path("frontend") / "src",
    Path("src"),
)
_MAX_LIGHTWEIGHT_TEXT_FILES = 80
_MAX_LIGHTWEIGHT_TEXT_BYTES = 128_000
_MAX_PATH_CANDIDATES = 120
_REPOSITORY_PATH_CACHE: dict[tuple[str, str, tuple[str, ...], int], tuple[str, ...]] = {}
_TRACKED_PATH_CACHE: dict[tuple[str, str], tuple[str, ...]] = {}
LOGGER = logging.getLogger("se_mentor.proposals.context")


@dataclass(frozen=True)
class ProposalContextResult:
    context_package: ContextPackage
    evidenced_paths: tuple[str, ...]
    revision: str


class ProposalContextBuilder:
    def __init__(self, session: Session, *, max_chars: int = 16000) -> None:
        self.session = session
        self.builder = ContextBuilder(max_chars=max_chars)

    def build_for_task(self, task_id: str, goal: str) -> ProposalContextResult:
        total_started = perf_counter()
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        project = self.session.get(Project, task.project_id)
        if project is None:
            raise ValueError("project not found")
        revision = task.base_revision or GitService(project.root_path).base_revision()
        keywords = _keywords(goal)
        repository_started = perf_counter()
        repository_items, paths = self._repository_items(project, revision, keywords)
        repository_ms = int((perf_counter() - repository_started) * 1000)
        knowledge_started = perf_counter()
        knowledge_items = self._knowledge_items(project.id, paths, keywords)
        knowledge_ms = int((perf_counter() - knowledge_started) * 1000)
        understanding_started = perf_counter()
        latest_understanding = self._latest_understanding(project.id)
        understanding_ms = int((perf_counter() - understanding_started) * 1000)
        if latest_understanding is not None:
            repository_items = (
                ContextItem(
                    f"project-understanding:{latest_understanding.id}",
                    "project_understanding",
                    latest_understanding.summary,
                    98,
                    TrustLabel.REPOSITORY_CONTENT,
                ),
                *repository_items,
            )
        build_started = perf_counter()
        package = self.builder.build(
            goal=goal,
            governance_items=(
                ContextItem(
                    "proposal-contract",
                    "governance",
                    (
                        "Return only JSON matching the proposal schema. Use only evidenced "
                        "existing repository paths from context. Prefer the smallest real "
                        "source path that can execute the requested change."
                    ),
                    100,
                    TrustLabel.SYSTEM,
                ),
            ),
            execution_policy=ContextItem(
                "proposal-boundary",
                "policy",
                "No file changes are authorized before proposal confirmation and governance.",
                100,
                TrustLabel.SYSTEM,
            ),
            current_error=ContextItem(
                "proposal-feedback",
                "feedback",
                "No prior proposal feedback.",
                90,
                TrustLabel.TOOL_OUTPUT,
            ),
            repository_items=repository_items,
            knowledge_items=knowledge_items,
        )
        build_ms = int((perf_counter() - build_started) * 1000)
        LOGGER.info(
            (
                "[perf] proposal.context.total task_id=%s project_id=%s duration_ms=%s "
                "repository_ms=%s knowledge_ms=%s project_understanding_ms=%s "
                "context_builder_ms=%s selected_files_count=%s context_chars=%s"
            ),
            task_id,
            project.id,
            int((perf_counter() - total_started) * 1000),
            repository_ms,
            knowledge_ms,
            understanding_ms,
            build_ms,
            len(paths),
            package.char_count,
        )
        return ProposalContextResult(package, tuple(sorted(paths)), revision)

    def build_for_revision(
        self,
        *,
        task_id: str,
        follow_up: str,
        current_proposal: ChangeProposal,
    ) -> ProposalContextResult:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        combined_goal = "\n".join(
            [
                task.original_request,
                current_proposal.goal,
                follow_up,
                current_proposal.initial_scope_json or "",
            ]
        )
        result = self.build_for_task(task_id, combined_goal)
        governance_items = tuple(
            item for item in result.context_package.items if item.section == "governance"
        )
        execution_policy = next(
            (item for item in result.context_package.items if item.section == "policy"),
            ContextItem(
                "proposal-boundary",
                "policy",
                "No file changes are authorized before proposal confirmation and governance.",
                100,
                TrustLabel.SYSTEM,
            ),
        )
        repository_items = tuple(
            item
            for item in result.context_package.items
            if item.section in {"repository", "code_index"}
        )
        knowledge_items = tuple(
            item for item in result.context_package.items if item.section == "knowledge"
        )
        package = self.builder.build(
            goal=combined_goal,
            governance_items=governance_items,
            execution_policy=execution_policy,
            current_error=ContextItem(
                f"proposal-revision:{current_proposal.id}",
                "feedback",
                json.dumps(
                    {
                        "original_request": task.original_request,
                        "current_proposal": {
                            "id": current_proposal.id,
                            "version": current_proposal.version,
                            "goal": current_proposal.goal,
                            "expected_behavior": current_proposal.expected_behavior,
                            "scope": _json_any(current_proposal.initial_scope_json, []),
                            "non_goals": _json_any(current_proposal.excluded_scope_json, []),
                            "constraints": _json_any(current_proposal.constraints_json, {}),
                            "risks": _json_any(current_proposal.risks_json, {}),
                            "acceptance": _json_any(current_proposal.acceptance_criteria_json, []),
                            "validation": _json_any(current_proposal.validation_plan_json, []),
                            "status": current_proposal.status,
                        },
                        "follow_up_instruction": follow_up,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                100,
                TrustLabel.TOOL_OUTPUT,
            ),
            repository_items=repository_items,
            knowledge_items=knowledge_items,
        )
        return ProposalContextResult(package, result.evidenced_paths, result.revision)

    def _repository_items(
        self,
        project: Project,
        revision: str,
        keywords: tuple[str, ...],
    ) -> tuple[tuple[ContextItem, ...], set[str]]:
        started = perf_counter()
        root = Path(project.root_path)
        code_index_started = perf_counter()
        symbols = self.session.scalars(
            select(CodeSymbol)
            .where(CodeSymbol.project_id == project.id)
            .where(CodeSymbol.revision == revision)
            .order_by(CodeSymbol.relative_path, CodeSymbol.qualified_name)
        ).all()
        code_index_ms = int((perf_counter() - code_index_started) * 1000)
        allow_migrations = _allow_migration_context(keywords)
        candidates = [
            symbol
            for symbol in symbols
            if allow_migrations or not _excluded_context_path(symbol.relative_path)
        ]
        matches = [symbol for symbol in candidates if _matches_symbol(symbol, keywords)]
        if not matches:
            matches = sorted(
                candidates,
                key=lambda symbol: (
                    _path_penalty(symbol.relative_path),
                    symbol.relative_path,
                    symbol.qualified_name,
                ),
            )[:12]
        paths = {symbol.relative_path for symbol in matches}
        file_selection_started = perf_counter()
        path_candidates = _indexed_path_candidates(
            root=root,
            project_id=project.id,
            revision=revision,
            keywords=keywords,
            symbols=tuple(candidates),
            understanding_paths=self._understanding_paths(project.id),
        )
        paths.update(path_candidates)
        file_selection_ms = int((perf_counter() - file_selection_started) * 1000)
        file_read_started = perf_counter()
        direct_text_matches, direct_stats = _direct_text_matches(root, keywords)
        direct_text_ms = int((perf_counter() - file_read_started) * 1000)
        paths.update(direct_text_matches)
        items: list[ContextItem] = [
            ContextItem(
                "git-baseline",
                "repository",
                json.dumps(
                    {
                        "revision": revision,
                        "status": GitService(root).status().__dict__,
                    },
                    sort_keys=True,
                    default=str,
                ),
                100,
                TrustLabel.REPOSITORY_CONTENT,
            )
        ]
        ranked_paths = sorted(paths, key=lambda path: (_path_penalty(path), path))[:8]
        snippet_read_count = 0
        for index, path in enumerate(ranked_paths, start=1):
            if _excluded_context_path(path) and not allow_migrations:
                continue
            source = _read_snippet(root / path)
            snippet_read_count += 1
            items.append(
                ContextItem(
                    f"file:{path}",
                    "repository",
                    json.dumps(
                        {
                            "path": path,
                            "semantic_context": _source_semantic_context(path, source),
                            "snippet": source,
                        },
                        sort_keys=True,
                    ),
                    90 - index,
                    TrustLabel.REPOSITORY_CONTENT,
                )
            )
        for symbol in [
            symbol
            for symbol in matches
            if allow_migrations or not _excluded_context_path(symbol.relative_path)
        ][:16]:
            items.append(
                ContextItem(
                    f"symbol:{symbol.id}",
                    "code_index",
                    json.dumps(
                        {
                            "path": symbol.relative_path,
                            "qualified_name": symbol.qualified_name,
                            "kind": symbol.kind,
                            "evidence": f"code-index://{revision}/{symbol.id}",
                        },
                        sort_keys=True,
                    ),
                    80,
                    TrustLabel.REPOSITORY_CONTENT,
                )
            )
        LOGGER.info(
            (
                "[perf] proposal.context.code_index project_id=%s duration_ms=%s "
                "symbols=%s matches=%s"
            ),
            project.id,
            code_index_ms,
            len(symbols),
            len(matches),
        )
        LOGGER.info(
            (
                "[perf] proposal.context.file_selection project_id=%s duration_ms=%s "
                "candidate_paths=%s selected_files_count=%s"
            ),
            project.id,
            file_selection_ms,
            len(path_candidates),
            len(paths),
        )
        LOGGER.info(
            (
                "[perf] proposal.context.file_read project_id=%s duration_ms=%s "
                "direct_scan_ms=%s read_files_count=%s text_files=%s text_bytes=%s"
            ),
            project.id,
            int((perf_counter() - file_read_started) * 1000),
            direct_text_ms,
            snippet_read_count,
            direct_stats["files"],
            direct_stats["bytes"],
        )
        LOGGER.info(
            (
                "[perf] proposal-context project_id=%s revision=%s total_ms=%s "
                "symbol_count=%s symbol_matches=%s path_candidates=%s text_files=%s "
                "text_bytes=%s text_matches=%s context_paths=%s context_bytes=%s "
                "estimated_tokens=%s code_evidence_count=%s memory_count=%s candidate_count=%s"
            ),
            project.id,
            revision,
            int((perf_counter() - started) * 1000),
            len(symbols),
            len(matches),
            len(path_candidates),
            direct_stats["files"],
            direct_stats["bytes"],
            len(direct_text_matches),
            len(ranked_paths),
            sum(len(item.text) for item in items),
            sum(len(item.text) for item in items) // 4,
            len(matches),
            0,
            len(paths),
        )
        return tuple(items), paths

    def _knowledge_items(
        self,
        project_id: str,
        paths: set[str],
        keywords: tuple[str, ...],
    ) -> tuple[ContextItem, ...]:
        started = perf_counter()
        hits = KnowledgeRetriever(self.session).search(
            project_id=project_id,
            paths=tuple(paths),
            keywords=keywords,
            limit=10,
        )
        items: list[ContextItem] = []
        for hit in hits:
            knowledge = self.session.get(EngineeringKnowledge, hit.knowledge_id)
            if knowledge is None:
                continue
            items.append(
                ContextItem(
                    f"knowledge:{knowledge.id}",
                    "knowledge",
                    json.dumps(
                        {
                            "key": knowledge.knowledge_key,
                            "status": knowledge.status,
                            "summary": knowledge.summary,
                            "score": hit.score,
                        },
                        sort_keys=True,
                    ),
                    75,
                    TrustLabel.TOOL_OUTPUT,
                )
            )
        LOGGER.info(
            (
                "[perf] proposal.context.knowledge project_id=%s duration_ms=%s "
                "paths=%s keywords=%s knowledge_hits=%s context_items=%s"
            ),
            project_id,
            int((perf_counter() - started) * 1000),
            len(paths),
            len(keywords),
            len(hits),
            len(items),
        )
        return tuple(items)

    def _latest_understanding(self, project_id: str) -> EngineeringKnowledge | None:
        return self.session.scalar(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == project_id)
            .where(EngineeringKnowledge.knowledge_key.like("project-understanding:%"))
            .order_by(EngineeringKnowledge.created_at.desc())
        )

    def _understanding_paths(self, project_id: str) -> tuple[str, ...]:
        latest = self._latest_understanding(project_id)
        if latest is None:
            return ()
        source = self.session.scalar(
            select(KnowledgeSource)
            .where(KnowledgeSource.knowledge_id == latest.id)
            .order_by(KnowledgeSource.created_at.desc())
        )
        if source is None:
            return ()
        data = _json_any(source.evidence_json, {})
        if not isinstance(data, dict):
            return ()
        paths: list[str] = []
        for key in ("entry_paths", "important_paths", "manifests", "modified_paths"):
            value = data.get(key)
            if isinstance(value, list):
                paths.extend(str(item) for item in value)
        return tuple(dict.fromkeys(path for path in paths if path))


def _keywords(text: str) -> tuple[str, ...]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
    words.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tuple(dict.fromkeys(words))


def _matches_symbol(symbol: CodeSymbol, keywords: tuple[str, ...]) -> bool:
    haystack = f"{symbol.relative_path} {symbol.qualified_name}".lower()
    return any(keyword in haystack for keyword in keywords)


def _indexed_path_candidates(
    *,
    root: Path,
    project_id: str,
    revision: str,
    keywords: tuple[str, ...],
    symbols: tuple[CodeSymbol, ...],
    understanding_paths: tuple[str, ...],
) -> set[str]:
    cache_key = (project_id, revision, keywords, len(symbols))
    cached = _REPOSITORY_PATH_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)
    matches: set[str] = set()
    candidate_paths = [
        *(symbol.relative_path for symbol in symbols),
        *understanding_paths,
        *_git_index_paths(root, project_id=project_id, revision=revision),
    ]
    for rel in candidate_paths[:_MAX_PATH_CANDIDATES]:
        if _excluded_context_path(rel) and not _allow_migration_context(keywords):
            continue
        rel_lower = rel.lower()
        if any(keyword.lower() in rel_lower for keyword in keywords):
            matches.add(rel)
    if not matches and understanding_paths:
        matches.update(understanding_paths[:8])
    result = tuple(sorted(matches, key=lambda path: (_path_penalty(path), path))[:12])
    _REPOSITORY_PATH_CACHE[cache_key] = result
    return set(result)


def _direct_text_matches(root: Path, keywords: tuple[str, ...]) -> tuple[set[str], dict[str, int]]:
    stats = {"files": 0, "bytes": 0}
    if not _simple_request(keywords):
        return set(), stats
    text_terms = _keyword_variants(
        tuple(
            keyword for keyword in keywords if any("\u4e00" <= char <= "\u9fff" for char in keyword)
        )
    )
    if not text_terms:
        return set(), stats
    matches: set[str] = set()
    for base in _LIGHTWEIGHT_TEXT_DIRS:
        start = root / base
        if not start.exists() or not start.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(name for name in dirnames if name not in _EXCLUDED_DIRS)
            for filename in sorted(filenames):
                if not filename.endswith(_FRONTEND_TEXT_EXTENSIONS):
                    continue
                if stats["files"] >= _MAX_LIGHTWEIGHT_TEXT_FILES:
                    return matches, stats
                path = Path(dirpath) / filename
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if stats["bytes"] + size > _MAX_LIGHTWEIGHT_TEXT_BYTES:
                    return matches, stats
                stats["files"] += 1
                stats["bytes"] += size
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(term in text for term in text_terms):
                    matches.add(path.relative_to(root).as_posix())
    return matches, stats


def _git_index_paths(root: Path, *, project_id: str, revision: str) -> tuple[str, ...]:
    cache_key = (project_id, revision)
    cached = _TRACKED_PATH_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ()
    paths = tuple(
        item.replace("\\", "/")
        for item in output.decode("utf-8", errors="ignore").split("\0")
        if item
    )[:_MAX_PATH_CANDIDATES]
    _TRACKED_PATH_CACHE[cache_key] = paths
    return paths


def _keyword_variants(keywords: tuple[str, ...]) -> tuple[str, ...]:
    variants = set(keywords)
    for keyword in keywords:
        if any("\u4e00" <= char <= "\u9fff" for char in keyword):
            variants.add("".join(f"\\u{ord(char):04x}" for char in keyword))
    return tuple(item for item in variants if item)


def _excluded_context_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _EXCLUDED_CONTEXT_PREFIXES)


def _allow_migration_context(keywords: tuple[str, ...]) -> bool:
    return any(keyword in _MIGRATION_KEYWORDS for keyword in keywords)


def _simple_request(keywords: tuple[str, ...]) -> bool:
    heavy_keywords = {
        "auth",
        "database",
        "migration",
        "schema",
        "security",
        "api",
        "backend",
        "persistence",
        "dependency",
    }
    return len(keywords) <= 6 and not any(keyword in heavy_keywords for keyword in keywords)


def _path_penalty(path: str) -> int:
    if path in {"frontend/src/app/fixtures.ts", "frontend/src/app/AppShell.tsx"}:
        return -30
    if path.startswith("frontend/src/app/"):
        return -20
    if path.startswith("frontend/src/components/"):
        return -15
    if path.startswith("frontend/src/pages/"):
        return -10
    if _excluded_context_path(path):
        return 50
    if path.startswith("docs/"):
        return 30
    if path.startswith("backend/"):
        return 20
    if "/test" in path or path.startswith("tests/"):
        return 10
    return 0


def _source_semantic_context(path: str, source: str) -> list[str]:
    haystack = f"{path}\n{source}".lower()
    contexts: list[str] = []
    for label, markers in (
        ("sidebar", ("sidebar", "<aside", "side-")),
        ("navigation", ("navitems", "<nav", 'className="nav', "navigation")),
        ("menu-item", ("label:", "key:", "nav-item")),
        ("page-heading", ("page-title", "<h1")),
        ("button", ("<button", "button")),
    ):
        if any(marker.lower() in haystack for marker in markers):
            contexts.append(label)
    return contexts


def _read_snippet(path: Path) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[:80])


def _json_any(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
