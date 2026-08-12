from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.models.governance import GovernanceDecision, ImpactReport
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus
from se_mentor.models.validation import ValidationPlan, ValidationRun

router = APIRouter(prefix="/api/tasks/{task_id}/evaluation", tags=["evaluation"])
_SESSION_FACTORY = get_session_factory()
FAILED_LABEL = "\u5931\u8d25"


@router.get("")
def task_evaluation(task_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        proposal = session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.task_id == task_id)
            .where(ChangeProposal.status != ProposalStatus.SUPERSEDED)
            .order_by(ChangeProposal.version.desc())
        ).first()
        impact = session.scalars(
            select(ImpactReport)
            .where(ImpactReport.task_id == task_id)
            .order_by(ImpactReport.created_at.desc())
        ).first()
        governance = session.scalars(
            select(GovernanceDecision)
            .where(GovernanceDecision.task_id == task_id)
            .order_by(GovernanceDecision.created_at.desc())
        ).first()
        plans = session.scalars(
            select(ValidationPlan)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationPlan.created_at.desc())
        ).all()
        runs = session.scalars(
            select(ValidationRun)
            .join(ValidationPlan, ValidationRun.validation_plan_id == ValidationPlan.id)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationRun.created_at.desc())
        ).all()
        has_evaluation = any((proposal, impact, governance, plans, runs))
        return ok(
            {
                "taskId": task.id,
                "hasEvaluation": has_evaluation,
                "overall": _overall(task, governance, runs, has_evaluation),
                "requirementCoverage": _requirement_coverage(task, proposal),
                "changeQuality": _change_quality(proposal, impact),
                "governance": _governance(governance),
                "validation": _validation(plans, runs),
                "evidence": _evidence(proposal, impact, governance, plans, runs),
            }
        )


def _overall(
    task: ChangeTask,
    governance: GovernanceDecision | None,
    runs: list[ValidationRun],
    has_evaluation: bool,
) -> dict[str, object]:
    if not has_evaluation:
        return {
            "status": "EMPTY",
            "title": "\u6682\u65e0\u8bc4\u4f30\u7ed3\u679c",
            "summary": "\u4efb\u52a1\u5b8c\u6210\u5e76\u4ea7\u751f\u8bc4\u4f30\u8bb0\u5f55\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002",
        }
    if any(run.status in {"FAILED", "ERROR"} for run in runs):
        status_value = "ATTENTION_REQUIRED"
        title = "\u9700\u8981\u5173\u6ce8"
    elif governance and governance.decision == "BLOCK":
        status_value = "BLOCKED"
        title = "\u6cbb\u7406\u963b\u6b62"
    elif task.status == "COMPLETED":
        status_value = "COMPLETED"
        title = "\u4efb\u52a1\u5df2\u5b8c\u6210"
    else:
        status_value = "IN_PROGRESS"
        title = "\u8bc4\u4f30\u8fdb\u884c\u4e2d"
    return {"status": status_value, "title": title, "summary": f"\u5f53\u524d\u4efb\u52a1\u72b6\u6001\uff1a{task.status}"}


def _requirement_coverage(
    task: ChangeTask,
    proposal: ChangeProposal | None,
) -> dict[str, object]:
    if proposal is None:
        return {
            "summary": "\u5c1a\u672a\u751f\u6210\u4fee\u6539\u65b9\u6848\uff0c\u65e0\u6cd5\u8bc4\u4f30\u9700\u6c42\u8986\u76d6\u3002",
            "covered": [],
            "uncovered": [task.original_request],
        }
    return {
        "summary": "\u9700\u6c42\u8986\u76d6\u6765\u81ea\u5f53\u524d\u65b9\u6848\u7684\u9a8c\u6536\u6761\u4ef6\u4e0e\u8303\u56f4\u3002",
        "covered": _json_items(proposal.acceptance_criteria_json),
        "uncovered": [],
    }


def _change_quality(
    proposal: ChangeProposal | None,
    impact: ImpactReport | None,
) -> dict[str, object]:
    if proposal is None and impact is None:
        return {"summary": "\u5c1a\u65e0\u4fee\u6539\u8d28\u91cf\u8bb0\u5f55\u3002", "scope": [], "risks": []}
    scope: list[Any] = _json_items(proposal.initial_scope_json) if proposal else []
    risks: list[Any] = _risk_items(proposal.risks_json) if proposal else []
    if impact is not None:
        scope.extend(_json_items(impact.direct_impacts_json))
        risks.extend(_uncertainty_items(impact.uncertainties_json))
    return {
        "summary": "\u4fee\u6539\u8d28\u91cf\u6839\u636e\u65b9\u6848\u8303\u56f4\u548c\u5f71\u54cd\u5206\u6790\u7ec4\u7ec7\u3002",
        "scope": _dedupe_items(scope),
        "risks": _dedupe_items(risks),
    }


def _governance(governance: GovernanceDecision | None) -> dict[str, object]:
    if governance is None:
        return {
            "decision": "\u672a\u8bc4\u4f30",
            "reason": "\u5c1a\u65e0\u6cbb\u7406\u7ed3\u679c\u3002",
            "requiresApproval": False,
        }
    return {
        "decision": _decision_label(governance.decision),
        "reason": _governance_reason(governance.reason_summary),
        "requiresApproval": governance.approval_required,
    }


def _validation(plans: list[ValidationPlan], runs: list[ValidationRun]) -> dict[str, object]:
    if not plans and not runs:
        return {
            "planned": [],
            "executed": [],
            "failed": [],
            "notRun": ["\u5c1a\u65e0\u9a8c\u8bc1\u8ba1\u5212\u6216\u6267\u884c\u8bb0\u5f55\u3002"],
        }
    planned: list[Any] = []
    for plan in plans:
        planned.extend(_json_items(plan.required_checks_json))
    executed = [f"{run.command_summary}\uff1a{_run_status_label(run.status)}" for run in runs]
    failed = [
        f"{run.command_summary}\uff1a{run.failure_category or FAILED_LABEL}"
        for run in runs
        if run.status in {"FAILED", "ERROR"}
    ]
    return {
        "planned": _dedupe_items(planned),
        "executed": executed,
        "failed": failed,
        "notRun": [] if runs else ["\u9a8c\u8bc1\u8ba1\u5212\u5c1a\u672a\u6267\u884c\u3002"],
    }


def _evidence(
    proposal: ChangeProposal | None,
    impact: ImpactReport | None,
    governance: GovernanceDecision | None,
    plans: list[ValidationPlan],
    runs: list[ValidationRun],
) -> dict[str, object]:
    summaries: list[str] = []
    technical: dict[str, object] = {}
    if proposal is not None:
        summaries.append("\u5f53\u524d\u65b9\u6848")
        technical["proposalId"] = proposal.id
    if impact is not None:
        summaries.append("\u5f71\u54cd\u5206\u6790")
        technical["impactEvidence"] = _json_object(impact.evidence_json)
    if governance is not None:
        summaries.append("\u6cbb\u7406\u51b3\u7b56")
        technical["governanceEvidence"] = _json_object(governance.evidence_json)
    if plans:
        summaries.append(f"{len(plans)} \u4e2a\u9a8c\u8bc1\u8ba1\u5212")
    if runs:
        summaries.append(f"{len(runs)} \u6761\u9a8c\u8bc1\u6267\u884c\u8bb0\u5f55")
    return {"summary": summaries, "technical": technical}


def _json_items(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return [str(data)]


def _risk_items(value: str | None) -> list[Any]:
    data = _json_object(value)
    items: list[Any] = []
    for key in ("risks", "inferences"):
        raw = data.get(key)
        if isinstance(raw, list):
            items.extend(raw)
        elif raw:
            items.append(str(raw))
    return items


def _uncertainty_items(value: str | None) -> list[Any]:
    data = _json_object(value)
    items: list[Any] = []
    for key in ("risks", "unknowns"):
        raw = data.get(key)
        if isinstance(raw, list):
            items.extend(raw)
        elif raw:
            items.append(str(raw))
    narrative = data.get("narrative")
    if narrative:
        items.append({"kind": "narrative", "summary": str(narrative)})
    return items


def _json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {"value": data}


def _decision_label(value: str) -> str:
    labels = {"ALLOW": "\u5141\u8bb8", "WARN": "\u9700\u8981\u786e\u8ba4", "BLOCK": "\u963b\u6b62"}
    return labels.get(value, value)


def _governance_reason(value: str) -> str:
    labels = {
        "Allowed within finite changed path scope.": "\u4fee\u6539\u8303\u56f4\u6709\u9650\uff0c\u7b26\u5408\u5f53\u524d\u6279\u51c6\u8303\u56f4\u3002",
        "Public or authentication-related changes require user approval.": "\u516c\u5171\u63a5\u53e3\u6216\u8ba4\u8bc1\u76f8\u5173\u4fee\u6539\u9700\u8981\u4f60\u7684\u786e\u8ba4\u3002",
        "Sensitive credential or environment files are blocked.": "\u654f\u611f\u51ed\u636e\u6216\u73af\u5883\u6587\u4ef6\u4fee\u6539\u5df2\u88ab\u963b\u6b62\u3002",
    }
    return labels.get(value, value)


def _run_status_label(value: str) -> str:
    labels = {
        "PASSED": "\u5df2\u901a\u8fc7",
        "FAILED": "\u5931\u8d25",
        "ERROR": "\u9519\u8bef",
        "SKIPPED": "\u5df2\u8df3\u8fc7",
        "INCONCLUSIVE": "\u65e0\u7ed3\u8bba",
    }
    return labels.get(value, value)


def _dedupe_items(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, ensure_ascii=True) if isinstance(value, (dict, list)) else str(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
