from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.main import create_app
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    GovernanceVerdict,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.llm import RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskStatus,
)


def test_project_governance_history_keeps_project_scoped_task_decisions() -> None:
    client = TestClient(create_app())
    factory = get_session_factory()
    root_token = uuid4().hex
    with session_scope(factory) as session:
        project_a = Project(root_path=f"C:/repo-a-{root_token}")
        project_b = Project(root_path=f"C:/repo-b-{root_token}")
        session.add_all([project_a, project_b])
        session.flush()
        task_a = _task(project_a.id, "修改任务菜单文案")
        task_b = _task(project_a.id, "调整认证逻辑")
        task_other = _task(project_b.id, "其他项目任务")
        session.add_all([task_a, task_b, task_other])
        session.flush()
        proposal_a = _proposal(task_a.id, 1, ["src/menu.py"])
        proposal_b = _proposal(task_b.id, 1, ["auth/middleware.py"])
        proposal_other = _proposal(task_other.id, 1, ["other.py"])
        session.add_all([proposal_a, proposal_b, proposal_other])
        session.flush()
        impact_a = _impact(task_a.id, proposal_a.id, ["src/menu.py"])
        impact_b = _impact(task_b.id, proposal_b.id, ["auth/middleware.py"])
        impact_other = _impact(task_other.id, proposal_other.id, ["other.py"])
        session.add_all([impact_a, impact_b, impact_other])
        session.flush()
        base = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
        first = _decision(
            task_a.id,
            impact_a.id,
            GovernanceVerdict.ALLOW,
            "Allowed within finite changed path scope.",
            ["src/menu.py"],
            base,
        )
        second = _decision(
            task_a.id,
            impact_a.id,
            GovernanceVerdict.BLOCK,
            "Sensitive credential or environment files are blocked.",
            [".env"],
            base + timedelta(minutes=1),
        )
        third = _decision(
            task_b.id,
            impact_b.id,
            GovernanceVerdict.WARN,
            "Public or authentication-related changes require user approval.",
            ["auth/middleware.py"],
            base + timedelta(minutes=2),
        )
        other = _decision(
            task_other.id,
            impact_other.id,
            GovernanceVerdict.ALLOW,
            "Allowed within finite changed path scope.",
            ["other.py"],
            base + timedelta(minutes=3),
        )
        session.add_all([first, second, third, other])
        session.flush()
        project_a_id = project_a.id
        task_a_id = task_a.id
        ids = [third.id, second.id, first.id]

    response = client.get(f"/api/projects/{project_a_id}/governance-history?limit=20")

    assert response.status_code == 200
    body = response.json()["data"]
    assert [item["governanceDecisionId"] for item in body["items"]] == ids
    assert [item["taskId"] for item in body["items"]].count(task_a_id) == 2
    assert all("evidence" not in item for item in body["items"])
    assert all("ruleHits" not in item for item in body["items"])
    assert body["items"][0]["decision"] == "WARN"
    assert body["items"][0]["reasonCode"] == "PUBLIC_OR_AUTH_CHANGE_REQUIRES_APPROVAL"
    assert body["items"][1]["blocked"] is True


def _task(project_id: str, request: str) -> ChangeTask:
    return ChangeTask(
        project_id=project_id,
        original_request=request,
        requester_id="test",
        status=TaskStatus.CREATED,
        version=1,
    )


def _proposal(task_id: str, version: int, scope: list[str]) -> ChangeProposal:
    return ChangeProposal(
        task_id=task_id,
        version=version,
        goal="goal",
        expected_behavior="expected",
        initial_scope_json=json.dumps(scope),
        acceptance_criteria_json="[]",
        completeness=ProposalCompleteness.COMPLETE,
        status=ProposalStatus.CONFIRMED,
        created_by_type=ProposalCreatedByType.SYSTEM,
    )


def _impact(task_id: str, proposal_id: str, paths: list[str]) -> ImpactReport:
    return ImpactReport(
        task_id=task_id,
        proposal_id=proposal_id,
        base_revision="test",
        direct_impacts_json=json.dumps([{"kind": "FILE", "relative_path": path} for path in paths]),
        evidence_json="[]",
        status=ImpactReportStatus.CURRENT,
    )


def _decision(
    task_id: str,
    impact_report_id: str,
    decision: GovernanceVerdict,
    reason: str,
    paths: list[str],
    created_at: datetime,
) -> GovernanceDecision:
    return GovernanceDecision(
        task_id=task_id,
        impact_report_id=impact_report_id,
        proposal_hash="a" * 64,
        revision="test",
        decision=decision,
        risk_level=RiskLevel.LOW,
        reason_summary=reason,
        allowed_scope_json=json.dumps(paths if decision != GovernanceVerdict.BLOCK else []),
        denied_scope_json=json.dumps(paths if decision == GovernanceVerdict.BLOCK else []),
        approval_required=decision == GovernanceVerdict.WARN,
        status=GovernanceDecisionStatus.ACTIVE,
        rule_set_version="rules-v1",
        evidence_json="{}",
        created_at=created_at,
    )
