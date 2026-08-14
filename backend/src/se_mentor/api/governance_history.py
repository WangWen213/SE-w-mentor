from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.governance import _governance_payload
from se_mentor.api.online_access import require_project_access
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.models.approval import ApprovalRequest, ApprovalRequestStatus
from se_mentor.models.governance import GovernanceDecision, GovernanceVerdict, ImpactReport
from se_mentor.models.task import ChangeProposal, ChangeTask

router = APIRouter(prefix="/api/projects", tags=["governance-history"])
_SESSION_FACTORY = get_session_factory()
LOGGER = logging.getLogger("se_mentor.api.governance_history")
_MAX_LIMIT = 30


@router.get("/{project_id}/governance-history")
def project_governance_history(
    project_id: str,
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    task_id: str | None = Query(None, alias="taskId"),
) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        db_started = perf_counter()
        if require_project_access(session, project_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        statement = (
            select(GovernanceDecision, ChangeTask, ImpactReport, ChangeProposal)
            .join(ChangeTask, GovernanceDecision.task_id == ChangeTask.id)
            .outerjoin(ImpactReport, GovernanceDecision.impact_report_id == ImpactReport.id)
            .outerjoin(ChangeProposal, ImpactReport.proposal_id == ChangeProposal.id)
            .where(ChangeTask.project_id == project_id)
            .order_by(GovernanceDecision.created_at.desc(), GovernanceDecision.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        if task_id:
            statement = statement.where(ChangeTask.id == task_id)
        rows = session.execute(statement).all()
        db_ms = int((perf_counter() - db_started) * 1000)
        serialization_started = perf_counter()
        visible_rows = rows[:limit]
        items = [
            _history_item(decision, task, impact_report, proposal)
            for decision, task, impact_report, proposal in visible_rows
        ]
        serialization_ms = int((perf_counter() - serialization_started) * 1000)
    LOGGER.info(
        "[perf] governance-history project_id=%s db_ms=%s serialization_ms=%s total_ms=%s count=%s",
        project_id,
        db_ms,
        serialization_ms,
        int((perf_counter() - started) * 1000),
        len(items),
    )
    return ok(
        {
            "projectId": project_id,
            "items": items,
            "limit": limit,
            "offset": offset,
            "hasMore": len(rows) > limit,
            "nextOffset": offset + len(items) if len(rows) > limit else None,
        }
    )


@router.get("/{project_id}/governance-history/{decision_id}")
def project_governance_detail(
    project_id: str,
    decision_id: str,
    request: Request,
    response: Response,
) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        db_started = perf_counter()
        if require_project_access(session, project_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        row = session.execute(
            select(GovernanceDecision, ChangeTask, ImpactReport)
            .join(ChangeTask, GovernanceDecision.task_id == ChangeTask.id)
            .outerjoin(ImpactReport, GovernanceDecision.impact_report_id == ImpactReport.id)
            .where(ChangeTask.project_id == project_id)
            .where(GovernanceDecision.id == decision_id)
        ).one_or_none()
        db_ms = int((perf_counter() - db_started) * 1000)
        if row is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("GOVERNANCE_DECISION_NOT_FOUND", "governance decision not found")
        decision, task, impact_report = row
        approval = session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.governance_decision_id == decision.id)
            .where(
                ApprovalRequest.status.in_(
                    [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.APPROVED]
                )
            )
        )
        proposal_id = impact_report.proposal_id if impact_report is not None else ""
        changed_paths = tuple(_decision_scope(decision, impact_report))
        serialization_started = perf_counter()
        payload = _governance_payload(
            proposal_id,
            changed_paths,
            impact_report,
            decision,
            approval,
        )
        payload["governanceDecisionId"] = decision.id
        payload["taskId"] = task.id
        serialization_ms = int((perf_counter() - serialization_started) * 1000)
    LOGGER.info(
        "[perf] governance-detail project_id=%s decision_id=%s db_ms=%s "
        "serialization_ms=%s total_ms=%s",
        project_id,
        decision_id,
        db_ms,
        serialization_ms,
        int((perf_counter() - started) * 1000),
    )
    return ok(payload)


def _history_item(
    decision: GovernanceDecision,
    task: ChangeTask,
    impact_report: ImpactReport | None,
    proposal: ChangeProposal | None,
) -> dict[str, object]:
    affected_paths = _decision_scope(decision, impact_report)
    reason_code = _reason_code(decision.reason_summary)
    return {
        "governanceDecisionId": decision.id,
        "taskId": task.id,
        "taskTitle": task.original_request,
        "proposalId": proposal.id if proposal is not None else None,
        "proposalVersion": proposal.version if proposal is not None else None,
        "decision": decision.decision,
        "affectedFileCount": len(set(affected_paths)),
        "reasonCode": reason_code,
        "displaySummary": _display_summary(reason_code, decision.reason_summary),
        "summary": _display_summary(reason_code, decision.reason_summary),
        "requiresApproval": bool(decision.approval_required),
        "blocked": decision.decision == GovernanceVerdict.BLOCK,
        "createdAt": decision.created_at.isoformat(),
    }


def _decision_scope(
    decision: GovernanceDecision,
    impact_report: ImpactReport | None,
) -> list[str]:
    scoped = _json_list(decision.allowed_scope_json) + _json_list(decision.denied_scope_json)
    if scoped:
        return scoped
    if impact_report is None:
        return []
    direct = _json_any(impact_report.direct_impacts_json, [])
    if not isinstance(direct, list):
        return []
    return [
        str(item.get("relative_path", ""))
        for item in direct
        if isinstance(item, dict) and item.get("relative_path")
    ]


def _reason_code(reason: str) -> str:
    labels = {
        "Allowed within finite changed path scope.": "FINITE_CHANGED_PATH_SCOPE",
        "Public or authentication-related changes require user approval.": (
            "PUBLIC_OR_AUTH_CHANGE_REQUIRES_APPROVAL"
        ),
        "Sensitive credential or environment files are blocked.": (
            "SENSITIVE_CREDENTIAL_OR_ENV_BLOCKED"
        ),
        "User warning requires approval.": "USER_WARNING_REQUIRES_APPROVAL",
        "Requested block verdict.": "REQUESTED_BLOCK_VERDICT",
    }
    return labels.get(reason, "UNKNOWN")


def _display_summary(reason_code: str, fallback: str) -> str:
    labels = {
        "FINITE_CHANGED_PATH_SCOPE": "修改范围有限，符合当前批准范围。",
        "PUBLIC_OR_AUTH_CHANGE_REQUIRES_APPROVAL": "公共接口或认证相关修改需要你的确认。",
        "SENSITIVE_CREDENTIAL_OR_ENV_BLOCKED": "敏感凭据或环境文件修改已被阻止。",
        "USER_WARNING_REQUIRES_APPROVAL": "本次操作需要你的确认。",
        "REQUESTED_BLOCK_VERDICT": "该操作已按阻止决策停止。",
    }
    return labels.get(reason_code, fallback or "暂未确定")


def _json_list(value: str | None) -> list[str]:
    data = _json_any(value, [])
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _json_any(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
