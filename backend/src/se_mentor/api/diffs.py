from __future__ import annotations

import difflib
import json
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_file_change_access, require_task_access
from se_mentor.api.runtime import get_runtime_settings, get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.models.execution import BackupEntry, FileChange, ToolExecution
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask
from se_mentor.runtime.profiles import RuntimeProfile

router = APIRouter(prefix="/api/diffs", tags=["diffs"])
_SESSION_FACTORY = get_session_factory()


@router.get("/tasks/{task_id}/changes")
def task_changes(task_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        project = session.get(Project, task.project_id)
        if project is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("FILE_CHANGE_EVIDENCE_MISSING", "file change has no project")
        changes = session.scalars(
            select(FileChange)
            .where(FileChange.task_id == task_id)
            .order_by(FileChange.created_at, FileChange.id)
        ).all()
        items = []
        for change in changes:
            tool = session.get(ToolExecution, change.tool_execution_id)
            if tool is None:
                continue
            backup = (
                session.get(BackupEntry, change.backup_entry_id) if change.backup_entry_id else None
            )
            items.append(_trace_payload(change, tool, task, project, backup))
        return ok({"taskId": task_id, "items": items, "count": len(items)})


@router.get("/{change_id}/trace")
def trace_change(change_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        change = require_file_change_access(session, change_id, request, response)
        if change is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("FILE_CHANGE_NOT_FOUND", "file change not found")
        tool = session.get(ToolExecution, change.tool_execution_id)
        if tool is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("FILE_CHANGE_EVIDENCE_MISSING", "file change has no tool execution")
        task = session.get(ChangeTask, change.task_id)
        if task is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("FILE_CHANGE_EVIDENCE_MISSING", "file change has no task")
        project = session.get(Project, task.project_id)
        if project is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("FILE_CHANGE_EVIDENCE_MISSING", "file change has no project")
        backup = (
            session.get(BackupEntry, change.backup_entry_id) if change.backup_entry_id else None
        )
        return ok(_trace_payload(change, tool, task, project, backup))


def _trace_payload(
    change: FileChange,
    tool: ToolExecution,
    task: ChangeTask,
    project: Project,
    backup: BackupEntry | None,
) -> dict[str, object]:
    before_text = _read_optional_text(Path(backup.backup_artifact_ref)) if backup else ""
    current_path = Path(project.root_path) / change.relative_path
    after_text = _read_optional_text(current_path)
    persisted_diff = _persisted_diff(tool)
    return {
        "changeId": change.id,
        "projectId": task.project_id,
        "taskId": task.id,
        "toolExecutionId": change.tool_execution_id,
        "actionId": change.action_id,
        "transactionId": tool.transaction_id,
        "filePath": change.relative_path,
        "relativePath": change.relative_path,
        "operation": change.change_type,
        "beforeHash": change.before_hash,
        "afterHash": change.after_hash,
        "diff": persisted_diff or _diff(change.relative_path, before_text, after_text),
        "evidence": {
            "toolName": tool.tool_name,
            "toolStatus": tool.status,
            "commandSummary": tool.command_summary,
            "backupRef": backup.backup_artifact_ref if backup else None,
            "workspacePath": None
            if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE
            else str(current_path),
        },
    }


def _persisted_diff(tool: ToolExecution) -> str:
    try:
        evidence = json.loads(tool.evidence_json)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(evidence, dict):
        return ""
    diff = evidence.get("diff")
    return diff if isinstance(diff, str) else ""


def _read_optional_text(path: Path) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _diff(relative_path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )
