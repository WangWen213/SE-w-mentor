from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import (
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
)
from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus
from se_mentor.proposals.review_service import ProposalReviewService


def test_AC_FR02_03_new_confirmed_proposal_supersedes_downstream_state(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "proposal-versioning.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        impact = ImpactReport(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            direct_impacts_json='["backend/src"]',
            evidence_json='[{"source":"test"}]',
            status=ImpactReportStatus.CURRENT,
        )
        request = ApprovalRequest(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            decision_revision=REVISION,
            proposal_hash=PROPOSAL_HASH,
            requested_scope_json='["backend/src"]',
            status=ApprovalRequestStatus.APPROVED,
            evidence_json='[{"source":"test"}]',
        )
        session.add_all([impact, request])
        session.flush()
        decision = session.get(GovernanceDecision, ids["decision_id"])
        assert decision is not None
        decision.impact_report_id = impact.id
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=request.id,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["backend/src"]',
            write_paths_json='["backend/src"]',
            protected_paths_json='[".env"]',
            commands_json='["pytest"]',
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":30}',
            invalidation_json='{"proposal_hash":"changed"}',
            evidence_json='[{"source":"test"}]',
        )
        newer = ChangeProposal(
            task_id=ids["task_id"],
            version=2,
            goal="Persist Phase 1 schema and review flow.",
            expected_behavior="Newly confirmed proposal invalidates old derived state.",
            initial_scope_json='["backend/src/se_mentor/proposals"]',
            acceptance_criteria_json='["old state is superseded"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.USER,
            supersedes_id=ids["proposal_id"],
        )
        session.add_all([policy, newer])
        session.flush()
        plan = ValidationPlan(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            execution_policy_id=policy.id,
            version=1,
            status=ValidationPlanStatus.ACTIVE,
            required_checks_json='["pytest"]',
            evidence_json='[{"source":"test"}]',
        )
        session.add(plan)
        session.flush()

        service = ProposalReviewService(session)
        assert service.can_write_execution(newer.id) is False
        result = service.confirm_new_version(newer.id, actor_id="user-1")
        task = session.get(ChangeTask, ids["task_id"])
        old = session.get(ChangeProposal, ids["proposal_id"])

    assert result.confirmed_proposal_id == newer.id
    assert result.superseded_proposal_ids == (ids["proposal_id"],)
    assert task is not None
    assert task.active_proposal_id == newer.id
    assert old is not None
    assert old.status == ProposalStatus.SUPERSEDED
    assert impact.status == ImpactReportStatus.SUPERSEDED
    assert decision.status == GovernanceDecisionStatus.SUPERSEDED
    assert request.status == ApprovalRequestStatus.SUPERSEDED
    assert policy.status == ExecutionPolicyStatus.SUPERSEDED
    assert policy.executable is False
    assert plan.status == ValidationPlanStatus.SUPERSEDED
    assert service.can_write_execution(newer.id) is True
