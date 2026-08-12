from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.context.context_builder import ContextBuilder, ContextItem, ContextPackage, TrustLabel
from se_mentor.git.git_service import GitService
from se_mentor.knowledge.retrieval import KnowledgeRetriever
from se_mentor.models.code_index import CodeIndex, CodeSymbol
from se_mentor.models.knowledge import EngineeringKnowledge
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
_MIGRATION_KEYWORDS = ("database", "schema", "migration", "migrate", "sql", "table", "model", "persistence")


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
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        project = self.session.get(Project, task.project_id)
        if project is None:
            raise ValueError("project not found")
        revision = task.base_revision or GitService(project.root_path).base_revision()
        keywords = _keywords(goal)
        repository_items, paths = self._repository_items(project, revision, keywords)
        knowledge_items = self._knowledge_items(project.id, paths, keywords)
        latest_understanding = self._latest_understanding(project.id)
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
        package = self.builder.build(
            goal=goal,
            governance_items=(
                ContextItem(
                    "proposal-contract",
                    "governance",
                    (
                        "Return only JSON matching the proposal schema. Use only evidenced existing "
                        "repository paths from context. If scope is unknown, state UNKNOWN in risks "
                        "instead of inventing paths."
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
        governance_items = tuple(item for item in result.context_package.items if item.section == "governance")
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
        knowledge_items = tuple(item for item in result.context_package.items if item.section == "knowledge")
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
        root = Path(project.root_path)
        symbols = self.session.scalars(
            select(CodeSymbol)
            .where(CodeSymbol.project_id == project.id)
            .where(CodeSymbol.revision == revision)
            .order_by(CodeSymbol.relative_path, CodeSymbol.qualified_name)
        ).all()
        allow_migrations = _allow_migration_context(keywords)
        candidates = [symbol for symbol in symbols if allow_migrations or not _excluded_context_path(symbol.relative_path)]
        matches = [symbol for symbol in candidates if _matches_symbol(symbol, keywords)]
        file_matches = _matching_files(root, keywords)
        if not matches:
            matches = sorted(candidates, key=lambda symbol: (_path_penalty(symbol.relative_path), symbol.relative_path, symbol.qualified_name))[:12]
        paths = {symbol.relative_path for symbol in matches}
        paths.update(file_matches)
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
        for index, path in enumerate(ranked_paths, start=1):
            if _excluded_context_path(path) and not allow_migrations:
                continue
            source = _read_snippet(root / path)
            items.append(
                ContextItem(
                    f"file:{path}",
                    "repository",
                    json.dumps({"path": path, "snippet": source}, sort_keys=True),
                    90 - index,
                    TrustLabel.REPOSITORY_CONTENT,
                )
            )
        for symbol in [
            symbol for symbol in matches if allow_migrations or not _excluded_context_path(symbol.relative_path)
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
        return tuple(items), paths

    def _knowledge_items(
        self,
        project_id: str,
        paths: set[str],
        keywords: tuple[str, ...],
    ) -> tuple[ContextItem, ...]:
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
        return tuple(items)

    def _latest_understanding(self, project_id: str) -> EngineeringKnowledge | None:
        return self.session.scalar(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == project_id)
            .where(EngineeringKnowledge.knowledge_key.like("project-understanding:%"))
            .order_by(EngineeringKnowledge.created_at.desc())
        )


def _keywords(text: str) -> tuple[str, ...]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
    return tuple(dict.fromkeys(words))


def _matches_symbol(symbol: CodeSymbol, keywords: tuple[str, ...]) -> bool:
    haystack = f"{symbol.relative_path} {symbol.qualified_name}".lower()
    return any(keyword in haystack for keyword in keywords)


def _matching_files(root: Path, keywords: tuple[str, ...]) -> set[str]:
    matches: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _EXCLUDED_DIRS)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            if _excluded_context_path(rel) and not _allow_migration_context(keywords):
                continue
            if any(keyword in rel.lower() for keyword in keywords):
                matches.add(rel)
    return matches


def _excluded_context_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _EXCLUDED_CONTEXT_PREFIXES)


def _allow_migration_context(keywords: tuple[str, ...]) -> bool:
    return any(keyword in _MIGRATION_KEYWORDS for keyword in keywords)


def _path_penalty(path: str) -> int:
    if _excluded_context_path(path):
        return 50
    if "/test" in path or path.startswith("tests/"):
        return 10
    return 0


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
