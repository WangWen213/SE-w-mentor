from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskStatus,
)
from se_mentor.proposals.completeness import CompletenessDecision, ProposalCompletenessService


def test_AC_FR02_02_incomplete_proposal_cannot_enter_analysis(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "completeness.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        incomplete = ChangeProposal(
            task_id=ids["task_id"],
            version=2,
            goal="",
            expected_behavior="",
            initial_scope_json="[]",
            acceptance_criteria_json="[]",
            constraints_json="[]",
            completeness=ProposalCompleteness.INCOMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        session.add(incomplete)
        session.flush()
        service = ProposalCompletenessService(session)
        decision = service.evaluate(incomplete.id)
        task = session.get(ChangeTask, ids["task_id"])

    assert decision.decision is CompletenessDecision.NEEDS_MORE_TECHNICAL_ANALYSIS
    assert decision.can_enter_analysis is False
    assert set(decision.missing) == {"goal", "expected_behavior", "scope", "acceptance"}
    assert task is not None
    assert task.status == TaskStatus.DECIDING
    assert task.failure_code == "NEEDS_MORE_TECHNICAL_ANALYSIS"


def test_phase1_completeness_separates_technical_unknowns_from_user_decisions(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "phase1-completeness.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        technical = ChangeProposal(
            task_id=ids["task_id"],
            version=2,
            goal="Improve memory output",
            current_problem='{"understanding":"Improve memory output for users"}',
            expected_behavior="Memory output is richer",
            initial_scope_json='["UNKNOWN"]',
            acceptance_criteria_json='["UI shows categorized memory"]',
            validation_plan_json='["Run frontend type-check"]',
            constraints_json=(
                '{"changes":[{"path":"backend/src/se_mentor/api/memory.py","symbol":null,'
                '"action":"TBD","reason":"Need to locate API contract"}],"steps":["Inspect memory API"],'
                '"constraints":[]}'
            ),
            risks_json='{"risks":["Compatibility risk"],"inferences":[]}',
            assumptions_json="{}",
            completeness=ProposalCompleteness.INCOMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        user_decision = ChangeProposal(
            task_id=ids["task_id"],
            version=3,
            goal="Improve memory output",
            current_problem='{"understanding":"Improve memory output for users"}',
            expected_behavior="Memory output is richer",
            initial_scope_json='["backend/src/se_mentor/api/memory.py"]',
            acceptance_criteria_json='["UI shows categorized memory"]',
            validation_plan_json='["Run frontend type-check"]',
            constraints_json=(
                '{"changes":[{"path":"backend/src/se_mentor/api/memory.py","symbol":null,'
                '"action":"Return categorized presentation fields","reason":"Frontend needs productized memory"}],'
                '"steps":["Inspect memory API","Map knowledge categories"],"constraints":[]}'
            ),
            risks_json='{"risks":["旧记忆兼容"],"inferences":[]}',
            assumptions_json='{"user_decisions":["是否允许用户手动删除工程记忆？"]}',
            completeness=ProposalCompleteness.INCOMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        complete = ChangeProposal(
            task_id=ids["task_id"],
            version=4,
            goal="Improve memory output",
            current_problem='{"understanding":"Improve memory output for users"}',
            expected_behavior="Memory output is richer",
            initial_scope_json='["backend/src/se_mentor/api/memory.py","frontend/src/pages/MemoryPage.tsx"]',
            acceptance_criteria_json='["UI shows categorized memory"]',
            validation_plan_json='["Run frontend type-check"]',
            constraints_json=(
                '{"changes":[{"path":"backend/src/se_mentor/api/memory.py","symbol":null,'
                '"action":"Return categorized presentation fields","reason":"Frontend needs productized memory"}],'
                '"steps":["Inspect memory API","Map knowledge categories"],"constraints":["Keep old records readable"]}'
            ),
            risks_json='{"risks":["旧记忆兼容"],"inferences":[]}',
            assumptions_json="{}",
            completeness=ProposalCompleteness.INCOMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        session.add_all([technical, user_decision, complete])
        session.flush()
        service = ProposalCompletenessService(session)

        technical_result = service.evaluate(technical.id)
        decision_result = service.evaluate(user_decision.id)
        complete_result = service.evaluate(complete.id)

    assert technical_result.decision is CompletenessDecision.NEEDS_MORE_TECHNICAL_ANALYSIS
    assert technical_result.technical_unknowns
    assert decision_result.decision is CompletenessDecision.NEEDS_USER_CLARIFICATION
    assert decision_result.user_decisions == ("是否允许用户手动删除工程记忆？",)
    assert complete_result.decision is CompletenessDecision.COMPLETE
    assert complete_result.can_enter_analysis is True
