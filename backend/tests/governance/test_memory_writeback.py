from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.governance.decision_service import GovernanceDecisionService
from se_mentor.governance.memory_writeback import GovernanceMemoryWritebackService
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.models.governance import (
    GovernanceRuleEffect,
    GovernanceRuleScope,
    GovernanceVerdict,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
)


def test_governance_rule_hit_writes_traceable_engineering_memory(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "governance-memory.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    rule = RuleDefinition(
        key="public-api",
        name="Public API warning",
        scope=GovernanceRuleScope.PROJECT,
        effect=GovernanceRuleEffect.REQUIRE_APPROVAL,
        priority=50,
        patterns=("backend/src/app/public_api.py",),
        conditions={},
        reason="Public API changes require user approval.",
        overridable=True,
    )

    with session_scope(session_factory) as session:
        decision = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            rules=(rule,),
            changed_paths=("backend/src/app/public_api.py",),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        decision.impact_report_id = _impact_report_id(session, ids["task_id"], ids["proposal_id"])

        result = GovernanceMemoryWritebackService(session).write_back(decision)
        skipped = GovernanceDecisionService(session).evaluate(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            proposal_hash="d" * 64,
            revision=REVISION,
            rules=(),
            changed_paths=("backend/src/app/service.py",),
            llm_verdict=GovernanceVerdict.ALLOW,
            user_verdict=None,
        )
        skipped_result = GovernanceMemoryWritebackService(session).write_back(skipped)

        assert result is not None
        knowledge = session.get(EngineeringKnowledge, result.knowledge_id)
        assert knowledge is not None
        source = session.query(KnowledgeSource).filter(KnowledgeSource.knowledge_id == knowledge.id).one()
        evidence = json.loads(source.evidence_json)

    assert result.category == "reusable_engineering_constraint"
    assert skipped_result is None
    assert knowledge.status == KnowledgeStatus.VERIFIED
    assert knowledge.scope_json == '["backend/src/app/public_api.py"]'
    assert "Public API changes require user approval." in knowledge.summary
    assert source.source_type == KnowledgeSourceType.GOVERNANCE_AUDIT
    assert evidence["sourceTaskId"] == ids["task_id"]
    assert evidence["sourceProposalId"] == ids["proposal_id"]
    assert evidence["sourceGovernanceDecisionId"] == decision.id
    assert evidence["category"] == "reusable_engineering_constraint"
    assert evidence["relatedPaths"] == ["backend/src/app/public_api.py"]
    assert evidence["freshness"] == "fresh"
    assert evidence["confidence"] == "verified"


def _impact_report_id(session, task_id: str, proposal_id: str) -> str:
    report = ImpactReport(
        task_id=task_id,
        proposal_id=proposal_id,
        base_revision=REVISION,
        direct_impacts_json='[{"relative_path":"backend/src/app/public_api.py"}]',
        evidence_json='[{"evidence_id":"proposal-scope:0"}]',
        status=ImpactReportStatus.CURRENT,
    )
    session.add(report)
    session.flush()
    return report.id
