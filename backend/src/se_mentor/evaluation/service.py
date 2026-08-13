from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.models.evaluation import TaskEvaluation, TaskEvaluationStatus
from se_mentor.models.execution import FileChange, TaskTransaction, TransactionState
from se_mentor.models.governance import GovernanceDecision, ImpactReport
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus
from se_mentor.models.validation import ValidationPlan, ValidationRun

FAILED_LABEL = "失败"


class EvaluationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def persist_for_task(self, task_id: str) -> TaskEvaluation | None:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            return None
        payload = self.build_payload(task)
        status_value = _evaluation_status(payload)
        existing = self.session.scalar(
            select(TaskEvaluation).where(TaskEvaluation.task_id == task.id)
        )
        if existing is None:
            existing = TaskEvaluation(
                project_id=task.project_id,
                task_id=task.id,
                status=status_value,
                summary_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
            self.session.add(existing)
        else:
            existing.status = status_value
            existing.summary_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._write_memory_projection(task, payload)
        self.session.flush()
        return existing

    def get_task_payload(self, task_id: str) -> dict[str, object] | None:
        row = self.session.scalar(select(TaskEvaluation).where(TaskEvaluation.task_id == task_id))
        if row is None:
            task = self.session.get(ChangeTask, task_id)
            return self.build_payload(task) if task is not None else None
        return _json_object(row.summary_json)

    def list_project_payloads(self, project_id: str) -> list[dict[str, object]]:
        rows = self.session.scalars(
            select(TaskEvaluation)
            .where(TaskEvaluation.project_id == project_id)
            .order_by(TaskEvaluation.created_at.desc())
        ).all()
        return [_json_object(row.summary_json) for row in rows]

    def build_payload(self, task: ChangeTask) -> dict[str, object]:
        proposal = self._proposal(task.id)
        impact = self._impact(task.id)
        governance = self._governance(task.id)
        plans = self._plans(task.id)
        runs = self._runs(task.id)
        changes = self._changes(task.id)
        transactions = self._transactions(task.id)
        has_evaluation = any((proposal, impact, governance, plans, runs, changes, transactions))
        return {
            "evaluationId": f"task:{task.id}",
            "projectId": task.project_id,
            "taskId": task.id,
            "taskTitle": task.original_request,
            "createdAt": (task.finished_at or task.updated_at or task.created_at).isoformat(),
            "hasEvaluation": has_evaluation,
            "overall": _overall(task, governance, runs, has_evaluation),
            "requirementCoverage": _requirement_coverage(task, proposal),
            "changeQuality": _change_quality(proposal, impact, changes),
            "governance": _governance_payload(governance),
            "validation": _validation(plans, runs),
            "execution": _execution_summary(changes, transactions),
            "memoryCandidates": _memory_candidates(task, governance, changes),
            "evidence": _evidence(proposal, impact, governance, plans, runs, changes),
        }

    def _proposal(self, task_id: str) -> ChangeProposal | None:
        return self.session.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.task_id == task_id)
            .where(ChangeProposal.status != ProposalStatus.SUPERSEDED)
            .order_by(ChangeProposal.version.desc())
        ).first()

    def _impact(self, task_id: str) -> ImpactReport | None:
        return self.session.scalars(
            select(ImpactReport)
            .where(ImpactReport.task_id == task_id)
            .order_by(ImpactReport.created_at.desc())
        ).first()

    def _governance(self, task_id: str) -> GovernanceDecision | None:
        return self.session.scalars(
            select(GovernanceDecision)
            .where(GovernanceDecision.task_id == task_id)
            .order_by(GovernanceDecision.created_at.desc())
        ).first()

    def _plans(self, task_id: str) -> list[ValidationPlan]:
        return self.session.scalars(
            select(ValidationPlan)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationPlan.created_at.desc())
        ).all()

    def _runs(self, task_id: str) -> list[ValidationRun]:
        return self.session.scalars(
            select(ValidationRun)
            .join(ValidationPlan, ValidationRun.validation_plan_id == ValidationPlan.id)
            .where(ValidationPlan.task_id == task_id)
            .order_by(ValidationRun.created_at.desc())
        ).all()

    def _changes(self, task_id: str) -> list[FileChange]:
        return self.session.scalars(
            select(FileChange).where(FileChange.task_id == task_id).order_by(FileChange.created_at)
        ).all()

    def _transactions(self, task_id: str) -> list[TaskTransaction]:
        return self.session.scalars(
            select(TaskTransaction)
            .where(TaskTransaction.task_id == task_id)
            .order_by(TaskTransaction.created_at.desc())
        ).all()

    def _write_memory_projection(self, task: ChangeTask, payload: dict[str, object]) -> None:
        changes = payload.get("changeQuality")
        scope = changes.get("scope", []) if isinstance(changes, dict) else []
        if not scope:
            return
        key = f"task-evaluation:{task.id}"
        existing = self.session.scalar(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == task.project_id)
            .where(EngineeringKnowledge.knowledge_key == key)
            .where(EngineeringKnowledge.version == 1)
        )
        if existing is not None:
            return
        KnowledgeRepository(self.session).add(
            project_id=task.project_id,
            key=key,
            knowledge_type=KnowledgeType.DECISION,
            status=KnowledgeStatus.REVIEWED,
            scope_paths=[str(item) for item in scope if isinstance(item, str)],
            summary=f"任务完成后沉淀的工程记忆：{task.original_request[:160]}",
            evidence_payloads=(_memory_evidence(payload),),
            source_type=KnowledgeSourceType.TEST,
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
            "title": "暂无评估结果",
            "summary": "任务完成并产生评估记录后会显示在这里。",
        }
    if any(run.status in {"FAILED", "ERROR"} for run in runs):
        status_value = "ATTENTION_REQUIRED"
        title = "需要关注"
    elif governance and governance.decision == "BLOCK":
        status_value = "BLOCKED"
        title = "治理阻止"
    elif task.status == "COMPLETED":
        status_value = "COMPLETED"
        title = "任务已完成"
    else:
        status_value = "IN_PROGRESS"
        title = "评估进行中"
    return {"status": status_value, "title": title, "summary": f"当前任务状态：{task.status}"}


def _requirement_coverage(
    task: ChangeTask,
    proposal: ChangeProposal | None,
) -> dict[str, object]:
    if proposal is None:
        return {
            "summary": "尚未生成修改方案，无法评估需求覆盖。",
            "covered": [],
            "uncovered": [task.original_request],
        }
    return {
        "summary": "需求覆盖来自当前方案的验收条件与范围。",
        "covered": _json_items(proposal.acceptance_criteria_json),
        "uncovered": [],
    }


def _change_quality(
    proposal: ChangeProposal | None,
    impact: ImpactReport | None,
    changes: list[FileChange],
) -> dict[str, object]:
    scope: list[Any] = _json_items(proposal.initial_scope_json) if proposal else []
    risks: list[Any] = _risk_items(proposal.risks_json) if proposal else []
    if impact is not None:
        scope.extend(_json_items(impact.direct_impacts_json))
        risks.extend(_uncertainty_items(impact.uncertainties_json))
    scope.extend(change.relative_path for change in changes)
    if not scope and not risks:
        return {"summary": "尚无修改质量记录。", "scope": [], "risks": []}
    return {
        "summary": "修改质量根据方案范围、影响分析和真实文件变更组织。",
        "scope": _dedupe_items(scope),
        "risks": _dedupe_items(risks),
    }


def _governance_payload(governance: GovernanceDecision | None) -> dict[str, object]:
    if governance is None:
        return {"decision": "未评估", "reason": "尚无治理结果。", "requiresApproval": False}
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
            "notRun": ["尚无验证计划或执行记录。"],
        }
    planned: list[Any] = []
    for plan in plans:
        planned.extend(_json_items(plan.required_checks_json))
    executed = [f"{run.command_summary}：{_run_status_label(run.status)}" for run in runs]
    failed = [
        f"{run.command_summary}：{run.failure_category or FAILED_LABEL}"
        for run in runs
        if run.status in {"FAILED", "ERROR"}
    ]
    return {
        "planned": _dedupe_items(planned),
        "executed": executed,
        "failed": failed,
        "notRun": [] if runs else ["验证计划尚未执行。"],
    }


def _execution_summary(
    changes: list[FileChange],
    transactions: list[TaskTransaction],
) -> dict[str, object]:
    committed = any(item.state == TransactionState.COMMITTED for item in transactions)
    return {
        "summary": "执行结果来自真实事务与文件变更记录。",
        "committed": committed,
        "changedFiles": [change.relative_path for change in changes],
    }


def _memory_candidates(
    task: ChangeTask,
    governance: GovernanceDecision | None,
    changes: list[FileChange],
) -> list[dict[str, object]]:
    if not changes:
        return []
    return [
        {
            "type": "工程决策",
            "summary": task.original_request,
            "sourceTaskId": task.id,
            "governanceDecision": governance.decision if governance is not None else None,
            "affectedPaths": [change.relative_path for change in changes],
        }
    ]


def _evidence(
    proposal: ChangeProposal | None,
    impact: ImpactReport | None,
    governance: GovernanceDecision | None,
    plans: list[ValidationPlan],
    runs: list[ValidationRun],
    changes: list[FileChange],
) -> dict[str, object]:
    summaries: list[str] = []
    technical: dict[str, object] = {}
    if proposal is not None:
        summaries.append("当前方案")
        technical["proposalId"] = proposal.id
    if impact is not None:
        summaries.append("影响分析")
        technical["impactEvidence"] = _json_object(impact.evidence_json)
    if governance is not None:
        summaries.append("治理决策")
        technical["governanceEvidence"] = _json_object(governance.evidence_json)
    if changes:
        summaries.append(f"{len(changes)} 个文件变更")
        technical["changedFiles"] = [change.relative_path for change in changes]
    if plans:
        summaries.append(f"{len(plans)} 个验证计划")
    if runs:
        summaries.append(f"{len(runs)} 条验证执行记录")
    return {"summary": summaries, "technical": technical}


def _evaluation_status(payload: dict[str, object]) -> str:
    overall = payload.get("overall")
    if isinstance(overall, dict) and overall.get("status") == "ATTENTION_REQUIRED":
        return TaskEvaluationStatus.PARTIAL
    return (
        TaskEvaluationStatus.COMPLETED
        if payload.get("hasEvaluation")
        else TaskEvaluationStatus.PARTIAL
    )


def _memory_evidence(payload: dict[str, object]) -> dict[str, object]:
    return {
        "evaluationId": payload.get("evaluationId"),
        "taskId": payload.get("taskId"),
        "taskTitle": payload.get("taskTitle"),
        "changeQuality": payload.get("changeQuality"),
        "governance": payload.get("governance"),
        "execution": payload.get("execution"),
    }


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


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {"value": data}


def _decision_label(value: str) -> str:
    labels = {"ALLOW": "允许", "WARN": "需要确认", "BLOCK": "阻止"}
    return labels.get(value, value)


def _governance_reason(value: str) -> str:
    labels = {
        "Allowed within finite changed path scope.": "修改范围有限，符合当前批准范围。",
        (
            "Public or authentication-related changes require user approval."
        ): "公共接口或认证相关修改需要你的确认。",
        (
            "Sensitive credential or environment files are blocked."
        ): "敏感凭据或环境文件修改已被阻止。",
    }
    return labels.get(value, value)


def _run_status_label(value: str) -> str:
    labels = {
        "PASSED": "已通过",
        "FAILED": "失败",
        "ERROR": "错误",
        "SKIPPED": "已跳过",
        "INCONCLUSIVE": "无结论",
    }
    return labels.get(value, value)


def _dedupe_items(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = (
            json.dumps(value, sort_keys=True, ensure_ascii=True)
            if isinstance(value, (dict, list))
            else str(value)
        )
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
