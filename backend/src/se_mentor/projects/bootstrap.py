from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.git.git_service import GitService
from se_mentor.indexing.file_inventory import build_file_inventory
from se_mentor.indexing.python_indexer import PythonIndexer
from se_mentor.indexing.relation_extractor import RelationExtractor
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)
from se_mentor.models.project import Project
from se_mentor.projects.toolchain_detector import detect_toolchain

LOGGER = logging.getLogger("se_mentor.project_bootstrap")


@dataclass(frozen=True)
class ProjectBootstrapResult:
    project_id: str
    revision: str
    file_count: int
    excluded_count: int
    symbol_count: int
    relation_count: int
    modified_count: int
    untracked_count: int
    toolchain_kind: str
    test_frameworks: tuple[str, ...]
    understanding_id: str


class ProjectBootstrapService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bootstrap(self, project_id: str) -> ProjectBootstrapResult:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError("project not found")
        root = Path(project.root_path).resolve()
        LOGGER.info("PROJECT_BOOTSTRAP START project_id=%s root=%s", project_id, root)
        git = GitService(root)
        LOGGER.info("PROJECT_BOOTSTRAP git START project_id=%s", project_id)
        revision = git.base_revision()
        status = git.status()
        LOGGER.info("PROJECT_BOOTSTRAP git DONE project_id=%s revision=%s", project_id, revision)
        LOGGER.info("PROJECT_BOOTSTRAP inventory START project_id=%s", project_id)
        inventory = build_file_inventory(root)
        LOGGER.info(
            "PROJECT_BOOTSTRAP inventory DONE project_id=%s files=%s excluded=%s limit=%s",
            project_id,
            len(inventory.files),
            len(inventory.excluded),
            inventory.limit_status,
        )
        LOGGER.info("PROJECT_BOOTSTRAP code_index START project_id=%s", project_id)
        index = PythonIndexer(self.session).build(project.id, root, revision)
        LOGGER.info(
            "PROJECT_BOOTSTRAP code_index DONE project_id=%s symbols=%s errors=%s",
            project_id,
            index.symbol_count,
            len(index.parse_errors),
        )
        LOGGER.info("PROJECT_BOOTSTRAP relations START project_id=%s", project_id)
        relations = RelationExtractor(self.session).extract(project.id, root, revision)
        LOGGER.info(
            "PROJECT_BOOTSTRAP relations DONE project_id=%s relations=%s unresolved=%s",
            project_id,
            relations.relation_count,
            len(relations.unresolved_edges),
        )
        LOGGER.info("PROJECT_BOOTSTRAP toolchain START project_id=%s", project_id)
        toolchain = detect_toolchain(root)
        LOGGER.info(
            "PROJECT_BOOTSTRAP toolchain DONE project_id=%s kind=%s frameworks=%s",
            project_id,
            toolchain.kind,
            toolchain.test_frameworks,
        )
        LOGGER.info("PROJECT_BOOTSTRAP understanding START project_id=%s", project_id)
        understanding = self._persist_understanding(
            project,
            revision=revision,
            file_count=len(inventory.files),
            excluded_count=len(inventory.excluded),
            inventory_limit_status=inventory.limit_status,
            inventory_total_size=inventory.total_size,
            symbol_count=index.symbol_count,
            parse_errors=index.parse_errors,
            relation_count=relations.relation_count,
            unresolved_relations=relations.unresolved_edges,
            modified_paths=status.modified,
            untracked_paths=status.untracked,
            toolchain_kind=str(toolchain.kind),
            manifests=toolchain.manifests,
            test_frameworks=toolchain.test_frameworks,
            toolchain_evidence=toolchain.evidence,
        )
        self.session.flush()
        LOGGER.info(
            "PROJECT_BOOTSTRAP DONE project_id=%s understanding_id=%s",
            project_id,
            understanding.id,
        )
        return ProjectBootstrapResult(
            project_id=project.id,
            revision=revision,
            file_count=len(inventory.files),
            excluded_count=len(inventory.excluded),
            symbol_count=index.symbol_count,
            relation_count=relations.relation_count,
            modified_count=len(status.modified),
            untracked_count=len(status.untracked),
            toolchain_kind=str(toolchain.kind),
            test_frameworks=toolchain.test_frameworks,
            understanding_id=understanding.id,
        )

    def _persist_understanding(self, project: Project, **values: object) -> EngineeringKnowledge:
        revision = str(values["revision"])
        key = f"project-understanding:{revision[:12]}"
        existing = self.session.scalar(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == project.id)
            .where(EngineeringKnowledge.knowledge_key == key)
        )
        evidence = _understanding_summary(project, values)
        if existing is not None:
            existing.summary = _human_understanding_summary(project, evidence)
            _upsert_understanding_evidence(self.session, existing, evidence)
            return existing
        return KnowledgeRepository(self.session).add(
            project_id=project.id,
            key=key,
            knowledge_type=KnowledgeType.CONSTRAINT,
            status=KnowledgeStatus.CANDIDATE,
            scope_paths=(),
            summary=_human_understanding_summary(project, evidence),
            evidence_payloads=(evidence,),
        )


def _understanding_summary(project: Project, values: dict[str, object]) -> dict[str, object]:
    manifests = _strings(values.get("manifests"))
    modified_paths = _strings(values.get("modified_paths"))
    untracked_paths = _strings(values.get("untracked_paths"))
    parse_errors = values.get("parse_errors")
    unresolved = values.get("unresolved_relations")
    important_paths = _important_paths(manifests, modified_paths, untracked_paths)
    return {
        "project_root": project.root_path,
        "revision": values.get("revision"),
        "file_count": values.get("file_count"),
        "excluded_count": values.get("excluded_count"),
        "inventory_limit_status": values.get("inventory_limit_status"),
        "symbol_count": values.get("symbol_count"),
        "relation_count": values.get("relation_count"),
        "parse_error_count": len(parse_errors) if isinstance(parse_errors, list) else 0,
        "unresolved_relation_count": len(unresolved) if isinstance(unresolved, list) else 0,
        "modified_count": len(modified_paths),
        "untracked_count": len(untracked_paths),
        "manifests": manifests[:20],
        "entry_paths": _entry_paths(manifests, important_paths),
        "important_paths": important_paths[:20],
        "modified_paths": modified_paths[:20],
        "toolchain_kind": values.get("toolchain_kind"),
        "test_frameworks": _strings(values.get("test_frameworks")),
        "toolchain_evidence": _compact_evidence(values.get("toolchain_evidence")),
    }


def _human_understanding_summary(project: Project, evidence: dict[str, object]) -> str:
    project_name = project.root_path.replace("\\", "/").rstrip("/").split("/")[-1] or "当前项目"
    toolchain = str(evidence.get("toolchain_kind") or "").split(".")[-1]
    stack = ", ".join(_strings(evidence.get("test_frameworks")))
    file_count = evidence.get("file_count")
    symbol_count = evidence.get("symbol_count")
    relation_count = evidence.get("relation_count")
    parts = [f"{project_name} 的项目理解候选记录来自本地仓库分析。"]
    if toolchain:
        parts.append(f"工具链类型：{toolchain}。")
    if stack:
        parts.append(f"测试体系：{stack}。")
    parts.append(f"索引规模：{file_count} 个文件，{symbol_count} 个符号，{relation_count} 条关系。")
    return " ".join(parts)[:2048]


def _upsert_understanding_evidence(
    session: Session,
    knowledge: EngineeringKnowledge,
    evidence: dict[str, object],
) -> None:
    source = session.scalar(
        select(KnowledgeSource)
        .where(KnowledgeSource.knowledge_id == knowledge.id)
        .where(KnowledgeSource.source_ref == f"{knowledge.knowledge_key}:evidence:1")
    )
    evidence_json = json.dumps(evidence, sort_keys=True, default=str)
    if source is None:
        session.add(
            KnowledgeSource(
                knowledge_id=knowledge.id,
                source_type=KnowledgeSourceType.TEST,
                source_ref=f"{knowledge.knowledge_key}:evidence:1",
                evidence_json=evidence_json,
            )
        )
    else:
        source.evidence_json = evidence_json
    session.flush()


def _entry_paths(manifests: list[str], important_paths: list[str]) -> list[str]:
    candidates = [
        path
        for path in (*manifests, *important_paths)
        if path.endswith(
            (
                "main.py",
                "app.py",
                "App.tsx",
                "main.tsx",
                "package.json",
                "pyproject.toml",
                "pom.xml",
                "application.yml",
                "application.yaml",
            )
        )
    ]
    return list(dict.fromkeys(candidates))[:12]


def _important_paths(
    manifests: list[str],
    modified_paths: list[str],
    untracked_paths: list[str],
) -> list[str]:
    return list(dict.fromkeys([*manifests, *modified_paths, *untracked_paths]))


def _strings(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _compact_evidence(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}:{str(item)[:80]}" for key, item in sorted(value.items())][:20]
    if isinstance(value, (list, tuple)):
        return [str(item)[:120] for item in value][:20]
    if value:
        return [str(value)[:120]]
    return []
