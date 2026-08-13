from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceRuleEffect,
    GovernanceRuleScope,
    GovernanceVerdict,
)
from se_mentor.models.llm import RiskLevel


def test_AC_FR06_05_deny_hard_overrides_llm_allow_and_user_warn(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "governance-decision.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    rules = (
        RuleDefinition(
            key="protect-env",
            name="Protect env",
            scope=GovernanceRuleScope.SYSTEM,
            effect=GovernanceRuleEffect.DENY_HARD,
            priority=100,
            patterns=(".env",),
            conditions={"path": True},
            reason="Credential files cannot be modified.",
            overridable=False,
        ),
        RuleDefinition(
            key="public-api",
            name="Public API warning",
            scope=GovernanceRuleScope.PROJECT,
            effect=GovernanceRuleEffect.REQUIRE_APPROVAL,
            priority=20,
            patterns=("backend/src/app/api.py",),
            conditions={"path": True},
            reason="Public API changes require review.",
            overridable=True,
        ),
    )

    with session_scope(session_factory) as session:
        service = GovernanceDecisionService(session)
        denied = service.evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=rules,
            changed_paths=(".env", "backend/src/app/api.py"),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=GovernanceVerdict.WARN,
        )
        allowed = service.evaluate(
            task_id=ids["task_id"],
            action_id=None,
            proposal_hash="c" * 64,
            revision=REVISION,
            rules=(),
            changed_paths=("backend/src/app/service.py",),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        stored = session.get(GovernanceDecision, denied.id)

    assert denied.decision == GovernanceVerdict.BLOCK
    assert denied.risk_level == RiskLevel.CRITICAL
    assert denied.approval_required is False
    assert "protect-env" in denied.evidence_json
    assert stored is not None
    assert stored.reason_summary == "Credential files cannot be modified."
    assert allowed.decision == GovernanceVerdict.ALLOW
    assert allowed.allowed_scope_json == '["backend/src/app/service.py"]'
    assert allowed.denied_scope_json == "[]"
