from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from se_mentor.approvals.request_service import ApprovalRequestService
from se_mentor.contracts.enums import ActionType
from se_mentor.evidence.bundle import EvidenceBundleBuilder, EvidenceItem
from se_mentor.git.git_service import GitService
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.impact.direct import DirectImpact, DirectImpactAnalyzer
from se_mentor.impact.indirect import IndirectImpactAnalyzer
from se_mentor.impact.report_service import ImpactReportService
from se_mentor.llm.base import LLMProvider
from se_mentor.models.approval import ApprovalRequest
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceRuleEffect,
    GovernanceRuleScope,
    GovernanceVerdict,
    ImpactReport,
)
from se_mentor.models.llm import AgentAction, AgentActionStatus, ParseStatus, RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    TaskIteration,
    TaskIterationPhase,
    TaskStatus,
)
from se_mentor.paths import canonical_project_paths
from se_mentor.policy.compiler import ExecutionPolicyCompiler
from se_mentor.proposals.review_service import ProposalReviewService
from se_mentor.runtime.profiles import RuntimeProfile, get_runtime_settings

LOGGER = logging.getLogger("se_mentor.orchestration.change_flow")


@dataclass(frozen=True)
class ConfirmFlowResult:
    proposal: ChangeProposal
    impact_report: ImpactReport
    governance_decision: GovernanceDecision
    approval_request: ApprovalRequest | None


class ChangeFlowOrchestrator:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def confirm_and_analyze(self, proposal_id: str, *, actor_id: str) -> ConfirmFlowResult:
        total_started = perf_counter()
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        confirm_started = perf_counter()
        ProposalReviewService(self.session).confirm_new_version(proposal_id, actor_id=actor_id)
        self.session.refresh(proposal)
        confirm_ms = int((perf_counter() - confirm_started) * 1000)
        LOGGER.info(
            "[perf] confirm.persist task_id=%s proposal_id=%s duration_ms=%s",
            proposal.task_id,
            proposal.id,
            confirm_ms,
        )
        task = proposal.task
        task.status = TaskStatus.GOVERNING
        scope = canonical_project_paths(_json_tuple(proposal.initial_scope_json))
        if not scope:
            raise ValueError("confirmed proposal has no impact scope")
        project = self.session.get(Project, task.project_id)
        if project is None:
            raise ValueError("project not found")
        revision = task.base_revision or GitService(project.root_path).base_revision()
        direct_started = perf_counter()
        diff_text = GitService(project.root_path).scoped_diff(list(scope))
        direct = DirectImpactAnalyzer(self.session).analyze(
            project_id=project.id,
            revision=revision,
            proposal_scope=scope,
            diff_text=diff_text,
        )
        direct_ms = int((perf_counter() - direct_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.code_index task_id=%s project_id=%s duration_ms=%s "
                "scope_count=%s direct_count=%s"
            ),
            task.id,
            project.id,
            direct_ms,
            len(scope),
            len(direct.impacts),
        )
        indirect_started = perf_counter()
        indirect = IndirectImpactAnalyzer(self.session).expand(
            project_id=project.id,
            revision=revision,
            direct_impacts=direct.impacts,
        )
        indirect_ms = int((perf_counter() - indirect_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.dependencies task_id=%s project_id=%s duration_ms=%s "
                "direct_count=%s indirect_count=%s unknown_count=%s"
            ),
            task.id,
            project.id,
            indirect_ms,
            len(direct.impacts),
            len(indirect.impacts),
            len(indirect.unknowns),
        )
        evidence_started = perf_counter()
        evidence_items = _evidence_items(
            revision=revision,
            direct_impacts=direct.impacts,
            indirect_refs=tuple(ref for impact in indirect.impacts for ref in impact.evidence_refs),
        )
        evidence_refs = tuple(item.evidence_id for item in evidence_items)
        bundle = EvidenceBundleBuilder(evidence_items).build(
            task_id=task.id,
            revision=revision,
            required_refs=evidence_refs,
            unresolved_assumptions=(*direct.unknowns, *indirect.unknowns),
        )
        evidence_ms = int((perf_counter() - evidence_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.context task_id=%s project_id=%s duration_ms=%s "
                "evidence_count=%s unresolved_count=%s"
            ),
            task.id,
            project.id,
            evidence_ms,
            len(evidence_items),
            len(direct.unknowns) + len(indirect.unknowns),
        )
        report_started = perf_counter()
        impact_report = ImpactReportService(self.session, self.provider).generate(
            task_id=task.id,
            proposal_id=proposal.id,
            base_revision=revision,
            evidence_bundle=bundle,
            direct_impacts=direct.impacts,
            indirect_impacts=indirect.impacts,
            unknowns=(*direct.unknowns, *indirect.unknowns),
        )
        report_ms = int((perf_counter() - report_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.analysis task_id=%s proposal_id=%s duration_ms=%s "
                "direct_count=%s indirect_count=%s"
            ),
            task.id,
            proposal.id,
            report_ms,
            len(direct.impacts),
            len(indirect.impacts),
        )
        action = _ensure_proposal_action(self.session, task, proposal, scope)
        governance_started = perf_counter()
        decision = GovernanceDecisionService(self.session).evaluate(
            task_id=task.id,
            action_id=action.id,
            proposal_hash=_proposal_hash(proposal),
            revision=revision,
            rules=_rules(),
            changed_paths=scope,
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        governance_ms = int((perf_counter() - governance_started) * 1000)
        LOGGER.info(
            (
                "[perf] governance.decision_call task_id=%s proposal_id=%s duration_ms=%s "
                "scope_count=%s decision=%s"
            ),
            task.id,
            proposal.id,
            governance_ms,
            len(scope),
            decision.decision,
        )
        decision.impact_report_id = impact_report.id
        approval_started = perf_counter()
        approval = ApprovalRequestService(self.session).create_for_decision(
            decision.id,
            requested_scope=scope,
        )
        if decision.decision == GovernanceVerdict.ALLOW:
            policy = ExecutionPolicyCompiler(self.session).compile(
                governance_decision_id=decision.id,
                read_paths=scope,
                write_paths=scope,
                commands=_execution_commands(),
                protected_paths=(),
                network={},
                resource_limits={},
            )
            task.active_policy_id = policy.id
            task.status = TaskStatus.ACTION_PENDING
        elif decision.decision == GovernanceVerdict.WARN:
            task.status = TaskStatus.APPROVAL_REQUIRED
        else:
            task.status = TaskStatus.BLOCKED
        self.session.flush()
        approval_policy_ms = int((perf_counter() - approval_started) * 1000)
        LOGGER.info(
            (
                "[perf] governance.policy_load task_id=%s proposal_id=%s duration_ms=%s "
                "approval_request=%s decision=%s"
            ),
            task.id,
            proposal.id,
            approval_policy_ms,
            approval is not None,
            decision.decision,
        )
        LOGGER.info(
            (
                "[perf] impact.total task_id=%s proposal_id=%s duration_ms=%s "
                "direct_ms=%s indirect_ms=%s context_ms=%s analysis_ms=%s"
            ),
            task.id,
            proposal.id,
            direct_ms + indirect_ms + evidence_ms + report_ms,
            direct_ms,
            indirect_ms,
            evidence_ms,
            report_ms,
        )
        LOGGER.info(
            (
                "[perf] governance.total task_id=%s proposal_id=%s duration_ms=%s "
                "decision_ms=%s persist_ms=%s"
            ),
            task.id,
            proposal.id,
            governance_ms + approval_policy_ms,
            governance_ms,
            approval_policy_ms,
        )
        LOGGER.info(
            (
                "[perf] confirm.total task_id=%s proposal_id=%s duration_ms=%s "
                "confirm_ms=%s impact_ms=%s governance_ms=%s"
            ),
            task.id,
            proposal.id,
            int((perf_counter() - total_started) * 1000),
            confirm_ms,
            direct_ms + indirect_ms + evidence_ms + report_ms,
            governance_ms + approval_policy_ms,
        )
        LOGGER.info(
            (
                "[perf] confirm-flow proposal_id=%s task_id=%s total_ms=%s "
                "confirm_ms=%s direct_ms=%s indirect_ms=%s evidence_ms=%s "
                "impact_report_ms=%s governance_ms=%s approval_policy_ms=%s "
                "scope_count=%s direct_count=%s indirect_count=%s decision=%s"
            ),
            proposal.id,
            task.id,
            int((perf_counter() - total_started) * 1000),
            confirm_ms,
            direct_ms,
            indirect_ms,
            evidence_ms,
            report_ms,
            governance_ms,
            approval_policy_ms,
            len(scope),
            len(direct.impacts),
            len(indirect.impacts),
            decision.decision,
        )
        return ConfirmFlowResult(proposal, impact_report, decision, approval)


def _ensure_proposal_action(
    session: Session,
    task: ChangeTask,
    proposal: ChangeProposal,
    scope: tuple[str, ...],
) -> AgentAction:
    existing = session.scalar(
        select(AgentAction).where(
            AgentAction.task_id == task.id,
            AgentAction.idempotency_key == f"proposal-governance:{proposal.id}",
        )
    )
    if existing is not None:
        return existing
    iteration_number = (
        session.scalar(
            select(func.max(TaskIteration.iteration_number)).where(TaskIteration.task_id == task.id)
        )
        or 0
    ) + 1
    iteration = TaskIteration(
        task_id=task.id,
        iteration_number=int(iteration_number),
        phase=TaskIterationPhase.ANALYZE,
    )
    session.add(iteration)
    session.flush()
    action = AgentAction(
        task_id=task.id,
        iteration_id=iteration.id,
        llm_call_id=None,
        action_sequence=1,
        action_type=ActionType.RUN_COMMAND,
        parameters_summary=json.dumps(
            {"proposal_id": proposal.id, "scope": scope, "command": "RUN_COMMAND"},
            sort_keys=True,
        ),
        schema_version="proposal-governance-v1",
        parse_status=ParseStatus.VALID,
        risk_level=RiskLevel.LOW,
        status=AgentActionStatus.GOVERNING,
        idempotency_key=f"proposal-governance:{proposal.id}",
    )
    session.add(action)
    session.flush()
    return action


def _evidence_items(
    *,
    revision: str,
    direct_impacts: tuple[DirectImpact, ...],
    indirect_refs: tuple[str, ...],
) -> tuple[EvidenceItem, ...]:
    refs = tuple(
        dict.fromkeys(
            [
                *(ref for impact in direct_impacts for ref in impact.evidence_refs),
                *indirect_refs,
            ]
        )
    )
    items: list[EvidenceItem] = []
    for ref in refs:
        items.append(
            EvidenceItem(
                evidence_id=ref,
                kind=_kind_for_ref(ref),
                revision=revision,
                uri=ref,
                summary=f"Repository evidence {ref}",
                freshness="fresh",
                confidence="confirmed" if "unknown" not in ref else "unknown",
                verified=True,
            )
        )
    return tuple(items)


def _kind_for_ref(ref: str) -> str:
    if ref.startswith("code-index://"):
        return "code-index"
    if ref.startswith("relation://"):
        return "relation"
    if ref.startswith("source://"):
        return "source"
    if ref.startswith("diff://"):
        return "diff"
    return "repository"


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


def _execution_commands() -> tuple[str, ...]:
    if get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE:
        return ("APPLY_APPROVED_CHANGES",)
    return ("RUN_COMMAND",)


def _proposal_hash(proposal: ChangeProposal) -> str:
    payload = {
        "id": proposal.id,
        "version": proposal.version,
        "scope": proposal.initial_scope_json,
        "acceptance": proposal.acceptance_criteria_json,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _json_tuple(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    data = json.loads(value)
    if isinstance(data, list):
        return tuple(str(item) for item in data)
    return ()
