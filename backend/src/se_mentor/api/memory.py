from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeSource
from se_mentor.models.project import Project

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])
_SESSION_FACTORY = get_session_factory()


@router.get("")
def list_knowledge(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        project = session.get(Project, project_id)
        if project is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        rows = session.scalars(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == project_id)
            .order_by(EngineeringKnowledge.created_at.desc())
        ).all()
        return ok(
            {
                "projectId": project_id,
                "items": [_knowledge_payload(session, row, project) for row in rows],
            }
        )


def _knowledge_payload(
    session: Session, row: EngineeringKnowledge, project: Project
) -> dict[str, object]:
    evidence = _project_understanding_evidence(session, row)
    return {
        "id": row.id,
        "key": row.knowledge_key,
        "type": row.knowledge_type,
        "status": row.status,
        "summary": row.summary,
        "scope": _json_list(row.scope_json),
        "evidenceRefs": _json_list(row.verified_evidence_json),
        "presentation": _presentation(row, project, evidence),
    }


def _presentation(
    row: EngineeringKnowledge,
    project: Project,
    evidence: dict[str, Any],
) -> dict[str, object] | None:
    if row.knowledge_key.startswith("task-evaluation:"):
        return _task_evaluation_presentation(row, evidence)
    if not row.knowledge_key.startswith("project-understanding:"):
        return _generic_presentation(row, evidence)
    sufficiency = _semantic_sufficiency(evidence)
    key_paths = _key_paths(evidence)
    return {
        "kind": "project-understanding",
        "title": "项目画像",
        "statusLabel": _status_label(row.status),
        "sufficiency": sufficiency,
        "summary": _overview(project, evidence, sufficiency),
        "projectType": _project_type(evidence),
        "techStack": _tech_stack(evidence),
        "structure": _structure(key_paths),
        "scale": _scale(evidence),
        "modules": _modules(key_paths),
        "keyPaths": key_paths,
        "tests": _tests(evidence),
        "gitBaseline": _git_baseline(evidence),
        "risks": _risks(evidence, sufficiency),
        "details": evidence or {"summary": row.summary},
    }


def _task_evaluation_presentation(
    row: EngineeringKnowledge,
    evidence: dict[str, Any],
) -> dict[str, object]:
    task_title = str(evidence.get("taskTitle") or row.summary)
    change_quality = evidence.get("changeQuality")
    governance = evidence.get("governance")
    execution = evidence.get("execution")
    scope = _strings(change_quality.get("scope")) if isinstance(change_quality, dict) else []
    changed_files = _strings(execution.get("changedFiles")) if isinstance(execution, dict) else []
    decision = governance.get("decision") if isinstance(governance, dict) else None
    reason = governance.get("reason") if isinstance(governance, dict) else None
    return {
        "kind": "engineering-decision",
        "title": "历史工程决策",
        "statusLabel": _status_label(row.status),
        "summary": task_title,
        "projectType": None,
        "techStack": [],
        "structure": [],
        "scale": [],
        "modules": [],
        "keyPaths": _dedupe([*scope, *changed_files])[:16],
        "tests": [],
        "gitBaseline": [],
        "risks": [str(reason)] if reason else [],
        "decision": str(decision) if decision else None,
        "details": evidence or {"summary": row.summary},
    }


def _generic_presentation(row: EngineeringKnowledge, evidence: dict[str, Any]) -> dict[str, object]:
    return {
        "kind": "engineering-memory",
        "title": _knowledge_type_label(row.knowledge_type),
        "statusLabel": _status_label(row.status),
        "summary": row.summary,
        "projectType": None,
        "techStack": [],
        "structure": [],
        "scale": [],
        "modules": [],
        "keyPaths": _json_list(row.scope_json),
        "tests": [],
        "gitBaseline": [],
        "risks": [],
        "details": evidence or {"summary": row.summary},
    }


def _project_understanding_evidence(
    session: Session,
    row: EngineeringKnowledge,
) -> dict[str, Any]:
    if not row.knowledge_key.startswith("project-understanding:"):
        return {}
    source = session.scalars(
        select(KnowledgeSource)
        .where(KnowledgeSource.knowledge_id == row.id)
        .order_by(KnowledgeSource.created_at.desc())
    ).first()
    if source is not None:
        evidence = _json_object(source.evidence_json)
        if evidence:
            return evidence
    return _json_object(row.summary)


def _semantic_sufficiency(evidence: dict[str, Any]) -> str:
    if not evidence:
        return "INSUFFICIENT"
    file_count = _int(evidence.get("file_count"))
    symbol_count = _int(evidence.get("symbol_count"))
    relation_count = _int(evidence.get("relation_count"))
    manifests = _strings(evidence.get("manifests"))
    has_source_manifest = any(
        path.endswith(("pyproject.toml", "requirements.txt", "package.json", "pom.xml"))
        for path in manifests
    )
    if not file_count:
        return "INSUFFICIENT"
    if has_source_manifest and not symbol_count and not relation_count:
        return "INSUFFICIENT"
    if symbol_count and (relation_count or manifests):
        return "SUFFICIENT"
    return "PARTIAL"


def _overview(project: Project, evidence: dict[str, Any], sufficiency: str) -> str:
    name = _project_name(project.root_path)
    if sufficiency == "INSUFFICIENT":
        return f"{name} 的工程画像仍需更多证据确认，当前只展示已从持久化记录中确认的信息。"
    if sufficiency == "PARTIAL":
        return f"{name} 的项目画像已根据已索引证据形成初步版本。"
    project_type = _project_type(evidence)
    if project_type:
        return f"{name}：已根据清单、工具链、代码索引和 Git 基线识别为 {project_type}。"
    return f"{name}：已根据当前持久化工程证据形成候选项目画像。"


def _project_type(evidence: dict[str, Any]) -> str | None:
    stack = set(_tech_stack(evidence))
    manifests = set(_strings(evidence.get("manifests")))
    if "React" in stack and "FastAPI" in stack:
        return "前后端混合项目"
    if "React" in stack:
        return "React 前端"
    if "FastAPI" in stack:
        return "Python 后端"
    if any(path.endswith("pom.xml") for path in manifests):
        return "Java 后端"
    if len(stack) > 1:
        return "混合项目"
    return next(iter(stack), None)


def _tech_stack(evidence: dict[str, Any]) -> list[str]:
    values: list[str] = []
    manifests = _strings(evidence.get("manifests"))
    frameworks = _strings(evidence.get("test_frameworks"))
    toolchain = str(evidence.get("toolchain_kind") or "")
    evidence_text = json.dumps(
        evidence.get("toolchain_evidence"), sort_keys=True, default=str
    ).lower()
    manifest_text = " ".join(manifests).lower()
    if "pyproject.toml" in manifest_text or "requirements" in manifest_text:
        values.append("Python")
    if "package.json" in manifest_text:
        values.append("TypeScript")
    if "pom.xml" in manifest_text:
        values.append("Java")
    if "fastapi" in evidence_text:
        values.append("FastAPI")
    if "react" in evidence_text:
        values.append("React")
    if "MIXED" in toolchain.upper():
        values.append("Mixed toolchain")
    values.extend(framework for framework in frameworks if framework)
    return _dedupe(values)


def _scale(evidence: dict[str, Any]) -> list[str]:
    labels = (("file_count", "文件"), ("symbol_count", "符号"), ("relation_count", "关系"))
    return [
        f"{value} {label}"
        for key, label in labels
        if (value := _int(evidence.get(key))) is not None
    ]


def _structure(key_paths: list[str]) -> list[str]:
    roots: list[str] = []
    for path in key_paths:
        first = path.replace("\\", "/").split("/", 1)[0]
        if first and "." not in first:
            roots.append(first)
    return _dedupe(roots)[:8]


def _modules(key_paths: list[str]) -> list[str]:
    modules: list[str] = []
    for path in key_paths:
        parts = path.replace("\\", "/").split("/")
        if len(parts) > 1 and "." not in parts[0]:
            modules.append(parts[0])
    return _dedupe(modules)[:8]


def _key_paths(evidence: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    paths.extend(_strings(evidence.get("entry_paths")))
    paths.extend(_strings(evidence.get("manifests")))
    paths.extend(_strings(evidence.get("important_paths")))
    paths.extend(_strings(evidence.get("modified_paths"))[:8])
    return _dedupe(path for path in paths if path and "UNKNOWN" not in path)[:16]


def _tests(evidence: dict[str, Any]) -> list[str]:
    frameworks = _strings(evidence.get("test_frameworks"))
    return frameworks if frameworks else ["尚未从工具链证据中确认测试框架。"]


def _git_baseline(evidence: dict[str, Any]) -> list[str]:
    values: list[str] = []
    revision = evidence.get("revision")
    if isinstance(revision, str) and revision:
        values.append(f"基线 revision {revision[:12]}")
    modified = _int(evidence.get("modified_count"))
    untracked = _int(evidence.get("untracked_count"))
    if modified is not None:
        values.append(f"{modified} 个已修改路径")
    if untracked is not None:
        values.append(f"{untracked} 个未跟踪路径")
    return values


def _risks(evidence: dict[str, Any], sufficiency: str) -> list[str]:
    risks: list[str] = []
    if sufficiency == "INSUFFICIENT":
        risks.append("结构化证据不足，核心模块识别仍需复核。")
    unresolved = _int(evidence.get("unresolved_relation_count"))
    if unresolved:
        risks.append(f"{unresolved} 个符号关系尚未解析。")
    parse_errors = _int(evidence.get("parse_error_count"))
    if parse_errors:
        risks.append(f"{parse_errors} 个解析错误。")
    limit_status = evidence.get("inventory_limit_status")
    if limit_status and str(limit_status).upper() not in {"OK", "COMPLETE"}:
        risks.append(f"文件清单状态：{limit_status}。")
    return risks or ["候选记忆仍需人工复核后才能视为已验证。"]


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, str):
        return _json_object(data)
    return data if isinstance(data, dict) else {}


def _status_label(status_value: str) -> str:
    labels = {
        "CANDIDATE": "待进一步确认",
        "FAILED_EXPERIENCE": "失败经验",
        "REVIEWED": "已复核",
        "STALE": "已过期",
        "VERIFIED": "已验证",
    }
    return labels.get(status_value, status_value)


def _knowledge_type_label(value: str) -> str:
    labels = {
        "CONSTRAINT": "工程约束",
        "DECISION": "工程决策",
        "FAILURE": "失败经验",
        "PATTERN": "工程模式",
    }
    return labels.get(value, value)


def _project_name(root_path: str) -> str:
    return root_path.replace("\\", "/").rstrip("/").split("/")[-1] or "Current project"


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _dedupe(values) -> list[str]:
    return list(dict.fromkeys(values))
