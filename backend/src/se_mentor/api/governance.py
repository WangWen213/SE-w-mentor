from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_proposal_access
from se_mentor.api.runtime import get_domain_provider, get_session_factory
from se_mentor.approvals.request_service import ApprovalRequestService
from se_mentor.db.session import session_scope
from se_mentor.evidence.bundle import EvidenceBundleBuilder, EvidenceItem
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.memory_writeback import GovernanceMemoryWritebackService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.impact.direct import DirectImpact, DirectImpactKind
from se_mentor.impact.report_service import ImpactReportGenerationError, ImpactReportService
from se_mentor.llm.base import ProviderError
from se_mentor.models.approval import (
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import (
    GovernanceDecisionStatus,
    GovernanceRuleEffect,
    GovernanceRuleScope,
    GovernanceVerdict,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus, TaskStatus
from se_mentor.orchestration.change_flow import _ensure_proposal_action
from se_mentor.policy.compiler import ExecutionPolicyCompiler

router = APIRouter(prefix="/api/proposals", tags=["governance"])
_SESSION_FACTORY = get_session_factory()


class GovernanceRequest(BaseModel):
    changed_paths: list[str] = Field(default_factory=list, alias="changedPaths")


@router.get("/{proposal_id}/governance")
def current_governance(
    proposal_id: str,
    request: Request,
    response: Response,
) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        proposal = require_proposal_access(session, proposal_id, request, response)
        if proposal is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        if proposal.status != ProposalStatus.CONFIRMED:
            response.status_code = status.HTTP_409_CONFLICT
            return error("PROPOSAL_NOT_CONFIRMED", "proposal must be confirmed before governance")
        changed_paths = tuple(_json_list(proposal.initial_scope_json))
        existing = _latest_governance(session, proposal.id)
        if existing is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("GOVERNANCE_NOT_FOUND", "governance result not found")
        impact_report, decision, approval = existing
        if not _impact_scope_matches(impact_report, changed_paths):
            response.status_code = status.HTTP_409_CONFLICT
            return error(
                "GOVERNANCE_SCOPE_STALE",
                "persisted governance scope does not match proposal",
            )
        approval = _ensure_execution_readiness(
            session,
            proposal=proposal,
            decision=decision,
            approval=approval,
            changed_paths=changed_paths,
        )
        return ok(
            _governance_payload(proposal_id, changed_paths, impact_report, decision, approval)
        )


@router.post("/{proposal_id}/governance")
def run_governance(
    proposal_id: str,
    payload: GovernanceRequest,
    request: Request,
    response: Response,
) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        proposal = require_proposal_access(session, proposal_id, request, response)
        if proposal is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROPOSAL_NOT_FOUND", "proposal not found")
        if proposal.status != ProposalStatus.CONFIRMED:
            response.status_code = status.HTTP_409_CONFLICT
            return error("PROPOSAL_NOT_CONFIRMED", "proposal must be confirmed before governance")
        changed_paths = tuple(payload.changed_paths or _json_list(proposal.initial_scope_json))
        existing = _latest_governance(session, proposal.id)
        if existing is not None:
            impact_report, decision, approval = existing
            if _impact_scope_matches(impact_report, changed_paths):
                approval = _ensure_execution_readiness(
                    session,
                    proposal=proposal,
                    decision=decision,
                    approval=approval,
                    changed_paths=changed_paths,
                )
                return ok(
                    _governance_payload(
                        proposal_id,
                        changed_paths,
                        impact_report,
                        decision,
                        approval,
                    )
                )
        if not changed_paths:
            _mark_governance_failed(
                session,
                proposal.task_id,
                "IMPACT_SCOPE_EMPTY",
                "confirmed proposal has no impact scope",
            )
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            return error("IMPACT_SCOPE_EMPTY", "confirmed proposal has no impact scope")
        try:
            impact_report = _generate_impact_report(session, proposal, changed_paths)
            action = _ensure_proposal_action(session, proposal.task, proposal, changed_paths)
            decision = GovernanceDecisionService(session).evaluate(
                task_id=proposal.task_id,
                action_id=action.id,
                proposal_hash=_proposal_hash(proposal),
                revision=proposal.task.base_revision or "working-tree",
                rules=_rules(),
                changed_paths=changed_paths,
                llm_verdict=GovernanceVerdict.ALLOW,
                user_verdict=None,
            )
            decision.impact_report_id = impact_report.id
            GovernanceMemoryWritebackService(session).write_back(decision)
            approval = _ensure_execution_readiness(
                session,
                proposal=proposal,
                decision=decision,
                approval=None,
                changed_paths=changed_paths,
            )
            session.flush()
            return ok(
                _governance_payload(proposal_id, changed_paths, impact_report, decision, approval)
            )
        except ProviderError as exc:
            _mark_governance_failed(session, proposal.task_id, exc.code, str(exc))
            response.status_code = status.HTTP_409_CONFLICT
            return error(
                exc.code if exc.code != "PROVIDER_AUTH" else "PROVIDER_UNAVAILABLE",
                str(exc),
            )
        except ImpactReportGenerationError as exc:
            _mark_governance_failed(session, proposal.task_id, "IMPACT_REPORT_FAILED", str(exc))
            response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            return error("IMPACT_REPORT_FAILED", str(exc))
        except Exception as exc:
            _mark_governance_failed(
                session,
                proposal.task_id,
                "GOVERNANCE_FAILED",
                str(exc) or "Governance failed",
            )
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return error("GOVERNANCE_FAILED", str(exc) or "Governance failed")


def _latest_governance(session, proposal_id: str):
    report = session.scalar(
        select(ImpactReport)
        .where(ImpactReport.proposal_id == proposal_id)
        .where(ImpactReport.status == ImpactReportStatus.CURRENT)
        .order_by(ImpactReport.created_at.desc())
    )
    if report is None:
        return None
    decision = next(
        (
            item
            for item in report.governance_decisions
            if item.status == GovernanceDecisionStatus.ACTIVE
        ),
        None,
    )
    if decision is None:
        return None
    approval = session.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.governance_decision_id == decision.id)
        .where(
            ApprovalRequest.status.in_(
                [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.APPROVED]
            )
        )
    )
    return report, decision, approval


def _ensure_execution_readiness(
    session,
    *,
    proposal: ChangeProposal,
    decision,
    approval: ApprovalRequest | None,
    changed_paths: tuple[str, ...],
) -> ApprovalRequest | None:
    if decision.action_id is None:
        action = _ensure_proposal_action(session, proposal.task, proposal, changed_paths)
        decision.action_id = action.id
        session.flush()
    if decision.decision != GovernanceVerdict.BLOCK:
        approval = approval or ApprovalRequestService(session).create_for_decision(
            decision.id,
            requested_scope=changed_paths,
        )
    if decision.decision == GovernanceVerdict.ALLOW:
        policy = _active_policy_for_decision(session, decision.id)
        if policy is None:
            policy = ExecutionPolicyCompiler(session).compile(
                governance_decision_id=decision.id,
                read_paths=changed_paths,
                write_paths=changed_paths,
                commands=("RUN_COMMAND",),
                protected_paths=(),
                network={},
                resource_limits={},
            )
        proposal.task.active_policy_id = policy.id
        proposal.task.status = TaskStatus.ACTION_PENDING
    elif decision.decision == GovernanceVerdict.WARN:
        proposal.task.status = TaskStatus.APPROVAL_REQUIRED
    else:
        proposal.task.status = TaskStatus.BLOCKED
    session.flush()
    return approval


def _active_policy_for_decision(session, decision_id: str) -> ExecutionPolicy | None:
    return session.scalar(
        select(ExecutionPolicy)
        .where(ExecutionPolicy.governance_decision_id == decision_id)
        .where(ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE)
    )


def _generate_impact_report(session, proposal: ChangeProposal, changed_paths: tuple[str, ...]):
    revision = proposal.task.base_revision or "working-tree"
    evidence_items = tuple(
        EvidenceItem(
            evidence_id=f"proposal-scope:{index}",
            kind="proposal-scope",
            revision=revision,
            uri=f"proposal://{proposal.id}/{path}",
            summary=f"Confirmed proposal scope includes {path}",
            freshness="fresh",
            confidence="confirmed",
            verified=True,
        )
        for index, path in enumerate(changed_paths)
    )
    bundle = EvidenceBundleBuilder(evidence_items).build(
        task_id=proposal.task_id,
        revision=revision,
        required_refs=tuple(item.evidence_id for item in evidence_items),
        unresolved_assumptions=tuple(
            str(item) for item in _json_object(proposal.assumptions_json).values()
        ),
    )
    direct_impacts = tuple(
        DirectImpact(
            DirectImpactKind.FILE,
            path,
            path,
            "confirmed",
            (evidence_items[index].evidence_id,),
        )
        for index, path in enumerate(changed_paths)
    )
    return ImpactReportService(session, get_domain_provider()).generate(
        task_id=proposal.task_id,
        proposal_id=proposal.id,
        base_revision=revision,
        evidence_bundle=bundle,
        direct_impacts=direct_impacts,
        indirect_impacts=(),
        unknowns=tuple(str(item) for item in _json_object(proposal.risks_json).get("risks", [])),
    )


def _governance_payload(
    proposal_id: str,
    changed_paths: tuple[str, ...],
    impact_report,
    decision,
    approval,
) -> dict[str, object]:
    direct = _json_any(impact_report.direct_impacts_json, []) if impact_report is not None else []
    indirect = (
        _json_any(impact_report.indirect_impacts_json, []) if impact_report is not None else []
    )
    uncertainties = (
        _json_any(impact_report.uncertainties_json, {}) if impact_report is not None else {}
    )
    evidence = _json_any(impact_report.evidence_json, []) if impact_report is not None else []
    return {
        "proposalId": proposal_id,
        "approvalRequestId": approval.id if approval is not None else None,
        "approvalStatus": approval.status if approval is not None else None,
        "decision": decision.decision,
        "changedPaths": sorted(changed_paths),
        "evidenceRef": f"impact-report://{impact_report.id}"
        if impact_report is not None
        else f"governance-decision://{decision.id}",
        "facts": [
            {
                "summary": f"{item.get('kind', 'FILE')} impact: {item.get('relative_path', '')}",
                "file": str(item.get("relative_path", "")),
                "line": 1,
            }
            for item in direct
        ],
        "inferences": (
            [str(uncertainties.get("narrative", ""))]
            if uncertainties.get("narrative")
            else []
        ),
        "unknowns": [str(item) for item in uncertainties.get("unknowns", [])],
        "evidence": [
            {
                "label": "impact_evidence",
                "detail": str(item.get("evidence_id", item)),
                "file": "impact-report",
                "line": 1,
            }
            for item in evidence
        ],
        "impactScope": {
            "files": sorted(changed_paths),
            "summary": f"{len(set(changed_paths))} 个文件受影响",
            "direct": direct,
            "indirect": indirect,
            "risks": [str(item) for item in uncertainties.get("risks", [])],
        },
        "ruleHits": _rule_hits_payload(decision.decision, decision.reason_summary),
        "nonApprovable": decision.decision == "BLOCK",
    }


def _rules() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition(
            key="sensitive-env",
            name="Sensitive env files",
            scope=GovernanceRuleScope.SYSTEM,
            effect=GovernanceRuleEffect.DENY_HARD,
            priority=100,
            patterns=(".env", "*.env", "*secret*"),
            conditions={},
            reason="Sensitive credential or environment files are blocked.",
            overridable=False,
        ),
        RuleDefinition(
            key="auth-public",
            name="Auth or public behavior",
            scope=GovernanceRuleScope.SYSTEM,
            effect=GovernanceRuleEffect.REQUIRE_APPROVAL,
            priority=50,
            patterns=("*auth*", "*public*"),
            conditions={},
            reason="Public or authentication-related changes require user approval.",
            overridable=True,
        ),
    )


def _rule_hits_payload(decision: str, reason: str) -> list[dict[str, str]]:
    return [{"level": decision, "label": decision, "reason": reason}]


def _proposal_hash(proposal: ChangeProposal) -> str:
    payload = {
        "id": proposal.id,
        "version": proposal.version,
        "scope": proposal.initial_scope_json,
        "acceptance": proposal.acceptance_criteria_json,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _mark_governance_failed(session, task_id: str, code: str, message: str) -> None:
    task = session.get(ChangeTask, task_id)
    if task is None:
        return
    task.status = TaskStatus.FAILED
    task.failure_code = code
    task.failure_message = message or "Governance failed"


def _impact_scope_matches(impact_report: ImpactReport, changed_paths: tuple[str, ...]) -> bool:
    direct = _json_any(impact_report.direct_impacts_json, [])
    paths = {
        str(item.get("relative_path", ""))
        for item in direct
        if isinstance(item, dict) and item.get("relative_path")
    }
    return set(changed_paths).issubset(paths)


def _json_list(value: str | None) -> list[str]:
    data = _json_any(value, [])
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _json_object(value: str | None) -> dict[str, object]:
    data = _json_any(value, {})
    if isinstance(data, dict):
        return data
    return {}


def _json_any(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
