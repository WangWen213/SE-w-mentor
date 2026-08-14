from __future__ import annotations

import json
import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_task_access
from se_mentor.api.runtime import (
    ONLINE_SAFE_EXECUTION_ERROR,
    get_runtime_settings,
    get_session_factory,
)
from se_mentor.db.session import session_scope
from se_mentor.git.git_service import GitService
from se_mentor.models.execution import FileChange, ToolExecution
from se_mentor.models.governance import GovernanceDecision, ImpactReport
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus
from se_mentor.models.validation import ValidationPlan, ValidationRun
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.runtime.profiles import RuntimeProfile
from se_mentor.tasks.task_service import TaskCreationRequest, TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
_SESSION_FACTORY = get_session_factory()
_TASK_SERVICE = TaskService(_SESSION_FACTORY)
LOGGER = logging.getLogger("se_mentor.api.tasks")


class TaskCreate(BaseModel):
    project_id: str = Field(alias="projectId")
    request: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, response: Response) -> dict[str, object]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        response.status_code = status.HTTP_409_CONFLICT
        return error(ONLINE_SAFE_EXECUTION_ERROR, "online safe execution is not ready")
    total_started = perf_counter()
    if not payload.request.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("TASK_REQUEST_REQUIRED", "task request is required")
    with session_scope(_SESSION_FACTORY) as session:
        project = session.get(Project, payload.project_id)
        if project is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        try:
            baseline_started = perf_counter()
            base_revision = GitService(project.root_path).base_revision()
            LOGGER.info(
                "[perf] task.create.git_baseline project_id=%s duration_ms=%s",
                payload.project_id,
                int((perf_counter() - baseline_started) * 1000),
            )
        except Exception as exc:
            LOGGER.exception("TASK_CREATE git baseline failed project_id=%s", payload.project_id)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("TASK_CREATE_FAILED", str(exc))
    try:
        persist_started = perf_counter()
        result = _TASK_SERVICE.create_task(
            TaskCreationRequest(
                project_id=payload.project_id,
                original_request=payload.request.strip(),
                requester_id="webui-user",
                base_revision=base_revision,
                token_budget=8192,
            ),
            actor_id="webui-user",
            idempotency_key=f"task-create:{uuid4()}",
        )
        LOGGER.info(
            "[perf] task.create.persist project_id=%s task_id=%s duration_ms=%s",
            payload.project_id,
            result.task_id,
            int((perf_counter() - persist_started) * 1000),
        )
    except ValueError as exc:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("TASK_CREATE_FAILED", str(exc))
    except Exception as exc:
        LOGGER.exception("TASK_CREATE failed project_id=%s", payload.project_id)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return error("TASK_CREATE_FAILED", str(exc))
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, result.task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        message_started = perf_counter()
        session.add(
            WorkbenchMessage(
                task_id=task.id,
                sequence=1,
                role="USER",
                kind="TEXT",
                status="DONE",
                text=task.original_request,
            )
        )
        payload_out = _task_payload(task)
        LOGGER.info(
            "[perf] task.create.message task_id=%s duration_ms=%s",
            task.id,
            int((perf_counter() - message_started) * 1000),
        )
    LOGGER.info(
        "[perf] task.create.total project_id=%s task_id=%s duration_ms=%s",
        payload.project_id,
        result.task_id,
        int((perf_counter() - total_started) * 1000),
    )
    return ok(payload_out)


@router.get("/{task_id}")
def get_task(task_id: str, request: Request, response: Response) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        payload_out = _task_payload(task)
    LOGGER.info("task.get task_id=%s total_ms=%s", task_id, int((perf_counter() - started) * 1000))
    return ok(payload_out)


@router.get("/{task_id}/timeline")
def get_task_timeline(task_id: str, request: Request, response: Response) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        db_started = perf_counter()
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        proposals = session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.task_id == task_id)
            .order_by(ChangeProposal.created_at, ChangeProposal.id)
        ).all()
        impacts = session.scalars(
            select(ImpactReport)
            .where(ImpactReport.task_id == task_id)
            .order_by(ImpactReport.created_at, ImpactReport.id)
        ).all()
        decisions = session.scalars(
            select(GovernanceDecision)
            .where(GovernanceDecision.task_id == task_id)
            .order_by(GovernanceDecision.created_at, GovernanceDecision.id)
        ).all()
        tools = session.scalars(
            select(ToolExecution)
            .where(ToolExecution.task_id == task_id)
            .order_by(ToolExecution.created_at, ToolExecution.id)
        ).all()
        changes = session.scalars(
            select(FileChange)
            .where(FileChange.task_id == task_id)
            .order_by(FileChange.created_at, FileChange.id)
        ).all()
        plans = session.scalars(
            select(ValidationPlan)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationPlan.created_at, ValidationPlan.id)
        ).all()
        runs = session.scalars(
            select(ValidationRun)
            .join(ValidationPlan, ValidationRun.validation_plan_id == ValidationPlan.id)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationRun.created_at, ValidationRun.id)
        ).all()
        db_ms = int((perf_counter() - db_started) * 1000)
        projection_started = perf_counter()
        items = _timeline_items(
            task=task,
            proposals=proposals,
            impacts=impacts,
            decisions=decisions,
            tools=tools,
            changes=changes,
            plans=plans,
            runs=runs,
        )
        projection_ms = int((perf_counter() - projection_started) * 1000)
        LOGGER.info(
            "task.timeline task_id=%s db_ms=%s projection_ms=%s total_ms=%s items=%s",
            task_id,
            db_ms,
            projection_ms,
            int((perf_counter() - started) * 1000),
            len(items),
        )
        return ok({"taskId": task_id, "items": items, "count": len(items)})


def _task_payload(task: ChangeTask) -> dict[str, object]:
    return {
        "id": task.id,
        "projectId": task.project_id,
        "request": task.original_request,
        "status": task.status,
    }


def _timeline_items(
    *,
    task: ChangeTask,
    proposals: list[ChangeProposal],
    impacts: list[ImpactReport],
    decisions: list[GovernanceDecision],
    tools: list[ToolExecution],
    changes: list[FileChange],
    plans: list[ValidationPlan],
    runs: list[ValidationRun],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for proposal in proposals:
        scope_count = len(_json_items(proposal.initial_scope_json))
        scope_body = (
            "\u5df2\u6574\u7406\u672c\u6b21\u4fee\u6539\u8303\u56f4\uff1a"
            f"{scope_count} \u4e2a\u6587\u4ef6\u3002"
        )
        items.append(
            _node(
                kind="PROPOSAL_READY",
                source_type="ChangeProposal",
                source_id=proposal.id,
                created_at=proposal.created_at,
                title="\u65b9\u6848\u5df2\u751f\u6210",
                body=scope_body,
                status="SUCCESS",
            )
        )
        if proposal.status == ProposalStatus.CONFIRMED:
            confirmed_body = (
                "\u6b63\u5728\u57fa\u4e8e\u786e\u8ba4\u8303\u56f4"
                "\u5206\u6790\u5f71\u54cd\u3002"
            )
            items.append(
                _node(
                    kind="PROPOSAL_CONFIRMED",
                    source_type="ChangeProposal",
                    source_id=proposal.id,
                    created_at=proposal.updated_at,
                    title="\u8303\u56f4\u5df2\u786e\u8ba4",
                    body=confirmed_body,
                    status="SUCCESS",
                    action={"label": "\u67e5\u770b\u6cbb\u7406", "target": "governance"},
                )
            )
    for impact in impacts:
        impact_count = len(_json_items(impact.direct_impacts_json))
        impact_body = f"\u786e\u8ba4\u5f71\u54cd {impact_count} \u4e2a\u6587\u4ef6\u3002"
        items.append(
            _node(
                kind="IMPACT_READY",
                source_type="ImpactReport",
                source_id=impact.id,
                created_at=impact.created_at,
                title="\u5f71\u54cd\u5206\u6790\u5b8c\u6210",
                body=impact_body,
                status="SUCCESS",
                action={"label": "\u67e5\u770b\u6cbb\u7406", "target": "governance"},
            )
        )
    for decision in decisions:
        is_non_display_action_allow = (
            decision.impact_report_id is None
            and decision.decision == "ALLOW"
            and not decision.approval_required
        )
        if is_non_display_action_allow:
            continue
        items.append(_governance_node(decision))
    location_node = _location_node(task.id, tools, changes)
    if location_node:
        items.append(location_node)
    write_tools = [
        tool
        for tool in tools
        if tool.tool_name in {"APPLY_PATCH", "CREATE_FILE", "DELETE_FILE"}
    ]
    for tool in write_tools:
        items.append(
            _node(
                kind="EXECUTION_STARTED",
                source_type="ToolExecution",
                source_id=tool.id,
                created_at=tool.created_at,
                title="\u5f00\u59cb\u6267\u884c\u4fee\u6539",
                body="\u6b63\u5728\u6309\u5df2\u786e\u8ba4\u8303\u56f4\u5199\u5165\u5de5\u4f5c\u533a\u3002",
                status="RUNNING" if tool.status == "RUNNING" else "SUCCESS",
            )
        )
    tools_by_id = {tool.id: tool for tool in tools}
    for change in changes:
        tool = tools_by_id.get(change.tool_execution_id)
        detail = _file_change_detail(change, tool)
        items.append(
            _node(
                kind="FILE_CHANGED",
                source_type="FileChange",
                source_id=change.id,
                created_at=change.created_at,
                title="\u6587\u4ef6\u4fee\u6539\u6210\u529f",
                body=detail,
                status="SUCCESS",
                action={"label": "\u67e5\u770b\u6539\u52a8", "target": "changes"},
            )
        )
    cancel_node = _cancel_node(task)
    if cancel_node:
        items.append(cancel_node)
    if plans and not runs:
        latest_plan = plans[-1]
        items.append(
            _node(
                kind="VALIDATION_STARTED",
                source_type="ValidationPlan",
                source_id=latest_plan.id,
                created_at=latest_plan.created_at,
                title="\u6b63\u5728\u68c0\u67e5\u4fee\u6539\u7ed3\u679c",
                body="\u5df2\u751f\u6210\u9a8c\u8bc1\u8ba1\u5212\uff0c\u7b49\u5f85\u6267\u884c\u7ed3\u679c\u3002",
                status="RUNNING",
                action={"label": "\u67e5\u770b\u68c0\u67e5", "target": "checks"},
            )
        )
    if runs:
        latest_run = runs[-1]
        passed = sum(1 for run in runs if run.status == "PASSED")
        failed = sum(1 for run in runs if run.status in {"FAILED", "ERROR"})
        status_value = "FAILED" if failed else "SUCCESS"
        items.append(
            _node(
                kind="VALIDATION_COMPLETED",
                source_type="ValidationRun",
                source_id=latest_run.id,
                created_at=latest_run.created_at,
                title="\u68c0\u67e5\u5b8c\u6210",
                body=f"{passed} \u9879\u901a\u8fc7 \u00b7 {failed} \u9879\u5931\u8d25\u3002",
                status=status_value,
                action={"label": "\u67e5\u770b\u68c0\u67e5", "target": "checks"},
            )
        )
    terminal = _terminal_node(task, changes)
    if terminal:
        items.append(terminal)
    items = _dedupe_nodes(items)
    items.sort(key=lambda item: (str(item["createdAt"]), str(item["id"])))
    for index, item in enumerate(items, start=1):
        item["sequence"] = index
    return items


def _governance_node(decision: GovernanceDecision) -> dict[str, object]:
    scope_count = len(_json_items(decision.allowed_scope_json))
    if decision.decision == "BLOCK":
        kind = "GOVERNANCE_BLOCK"
        title = "\u6267\u884c\u5df2\u963b\u6b62"
        body = _governance_reason(decision.reason_summary)
        status_value = "FAILED"
    elif decision.approval_required or decision.decision == "WARN":
        kind = "GOVERNANCE_APPROVAL_REQUIRED"
        title = "\u9700\u8981\u4f60\u7684\u786e\u8ba4"
        body = _governance_reason(decision.reason_summary)
        status_value = "WAITING"
    else:
        kind = "GOVERNANCE_ALLOW"
        title = "\u6cbb\u7406\u68c0\u67e5\u5b8c\u6210"
        body = (
            "\u81ea\u52a8\u5141\u8bb8 \u00b7 "
            f"\u5f71\u54cd {scope_count} \u4e2a\u6587\u4ef6\u3002"
        )
        status_value = "SUCCESS"
    return _node(
        kind=kind,
        source_type="GovernanceDecision",
        source_id=decision.id,
        created_at=decision.created_at,
        title=title,
        body=body,
        status=status_value,
        action={"label": "\u67e5\u770b\u6cbb\u7406", "target": "governance"},
    )


def _location_node(
    task_id: str,
    tools: list[ToolExecution],
    changes: list[FileChange],
) -> dict[str, object] | None:
    read_tools = [tool for tool in tools if tool.tool_name in {"SEARCH_CODE", "READ_FILE"}]
    if not read_tools:
        return None
    located_path = _first_located_path(read_tools) or (
        changes[0].relative_path if changes else ""
    )
    kind = "TARGET_LOCATED" if located_path else "LOCATING"
    title = (
        "\u5df2\u5b9a\u4f4d\u76ee\u6807"
        if located_path
        else "\u6b63\u5728\u5b9a\u4f4d\u4fee\u6539\u4f4d\u7f6e"
    )
    body = (
        f"{located_path}\n"
        "\u8be5\u4f4d\u7f6e\u5bf9\u5e94\u672c\u6b21\u9700\u8981"
        "\u8c03\u6574\u7684\u754c\u9762\u914d\u7f6e\u3002"
        if located_path
        else (
            "\u6b63\u5728\u6839\u636e\u4ee3\u7801\u8bc1\u636e"
            "\u7f29\u5c0f\u4fee\u6539\u8303\u56f4\u3002"
        )
    )
    return _node(
        kind=kind,
        source_type="ToolExecution",
        source_id=f"{task_id}:location",
        created_at=read_tools[0].created_at,
        title=title,
        body=body,
        status="SUCCESS" if located_path else "RUNNING",
    )


def _terminal_node(task: ChangeTask, changes: list[FileChange]) -> dict[str, object] | None:
    timestamp = task.finished_at or task.updated_at or task.created_at
    changed_count = len(changes)
    if task.status == "COMPLETED":
        return _node(
            kind="TASK_COMPLETED",
            source_type="ChangeTask",
            source_id=f"{task.id}:completed",
            created_at=timestamp,
            title="\u4efb\u52a1\u5b8c\u6210",
            body=(
                f"\u5df2\u4fee\u6539 {changed_count} \u4e2a\u6587\u4ef6\uff0c"
                "\u6539\u52a8\u5df2\u5199\u5165\u5de5\u4f5c\u533a\u3002"
            ),
            status="SUCCESS",
        )
    if task.status in {"FAILED", "BLOCKED", "CANCELLED"}:
        body = (
            task.failure_message
            or "\u6ca1\u6709\u4ea7\u751f\u6240\u9700\u6587\u4ef6\u6539\u52a8\u3002"
        )
        return _node(
            kind="TASK_FAILED",
            source_type="ChangeTask",
            source_id=f"{task.id}:failed",
            created_at=timestamp,
            title="\u6267\u884c\u672a\u5b8c\u6210",
            body=body,
            status="FAILED",
        )
    if changes:
        return _node(
            kind="TASK_STATUS",
            source_type="ChangeTask",
            source_id=f"{task.id}:current-status",
            created_at=timestamp,
            title="\u4efb\u52a1\u4ecd\u5728\u8fdb\u884c",
            body="\u5df2\u8bb0\u5f55\u771f\u5b9e\u6587\u4ef6\u6539\u52a8\uff0c\u540e\u7eed\u9a8c\u8bc1\u6216\u5b8c\u6210\u4e8b\u5b9e\u5c1a\u672a\u5199\u5165\u3002",
            status="RUNNING",
        )
    return None


def _cancel_node(task: ChangeTask) -> dict[str, object] | None:
    if task.status != "CANCELLED":
        return None
    return _node(
        kind="TASK_CANCELLED",
        source_type="ChangeTask",
        source_id=f"{task.id}:cancelled",
        created_at=task.updated_at or task.created_at,
        title="\u4efb\u52a1\u5df2\u505c\u6b62",
        body=(
            task.failure_message
            or "\u540e\u7aef\u5df2\u5728\u5b89\u5168\u70b9\u505c\u6b62\u4efb\u52a1\u3002"
        ),
        status="FAILED",
    )


def _node(
    *,
    kind: str,
    source_type: str,
    source_id: str,
    created_at,
    title: str,
    body: str,
    status: str,
    action: dict[str, str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": f"{source_type}:{source_id}:{kind}",
        "kind": kind,
        "source": {"type": source_type, "id": source_id},
        "createdAt": created_at.isoformat(),
        "title": title,
        "body": body,
        "status": status,
    }
    if action:
        payload["action"] = action
    return payload


def _file_change_detail(change: FileChange, tool: ToolExecution | None) -> str:
    diff = _persisted_diff(tool) if tool else ""
    summary = _diff_summary(diff)
    if summary:
        return f"{change.relative_path}\n{summary}"
    return change.relative_path


def _diff_summary(diff: str) -> str:
    removed = ""
    added = ""
    for line in diff.splitlines():
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-") and not removed:
            removed = _display_diff_value(line[1:])
        elif line.startswith("+") and not added:
            added = _display_diff_value(line[1:])
        if removed and added:
            break
    if removed and added:
        return f"{removed} -> {added}"
    return ""


def _display_diff_value(value: str) -> str:
    decoded = _decode_unicode_escapes(value.strip().strip(","))
    label_match = re.search(r'label:\s*"([^"]+)"', decoded)
    if label_match:
        return label_match.group(1)
    return decoded


def _decode_unicode_escapes(value: str) -> str:
    return re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def _persisted_diff(tool: ToolExecution) -> str:
    evidence = _json_object(tool.evidence_json)
    diff = evidence.get("diff")
    return diff if isinstance(diff, str) else ""


def _first_located_path(tools: list[ToolExecution]) -> str:
    for tool in tools:
        evidence = _json_object(tool.evidence_json)
        result = evidence.get("result")
        if isinstance(result, dict):
            matches = result.get("matches")
            if isinstance(matches, list):
                for match in matches:
                    if isinstance(match, dict) and isinstance(match.get("path"), str):
                        return str(match["path"])
        relative_path = evidence.get("relative_path")
        if isinstance(relative_path, str):
            return relative_path
    return ""


def _governance_reason(value: str) -> str:
    labels = {
        "Allowed within finite changed path scope.": (
            "\u4fee\u6539\u8303\u56f4\u6709\u9650\uff0c"
            "\u7b26\u5408\u5f53\u524d\u6279\u51c6\u8303\u56f4\u3002"
        ),
        "Public or authentication-related changes require user approval.": (
            "\u672c\u6b21\u64cd\u4f5c\u89e6\u53d1\u4e86"
            "\u9700\u8981\u6388\u6743\u7684\u89c4\u5219\u3002"
        ),
        "Sensitive credential or environment files are blocked.": (
            "\u654f\u611f\u51ed\u636e\u6216\u73af\u5883\u6587\u4ef6"
            "\u4fee\u6539\u5df2\u88ab\u963b\u6b62\u3002"
        ),
    }
    return labels.get(value, value)


def _json_items(value: str | None) -> list[object]:
    data = _json_value(value)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return [data] if data else []


def _json_object(value: str | None) -> dict[str, object]:
    data = _json_value(value)
    return data if isinstance(data, dict) else {}


def _json_value(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _dedupe_nodes(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for item in items:
        key = str(item["id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
