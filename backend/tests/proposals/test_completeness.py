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

    assert decision.decision is CompletenessDecision.NEEDS_INFORMATION
    assert decision.can_enter_analysis is False
    assert set(decision.missing) == {"goal", "expected_behavior", "scope", "acceptance"}
    assert task is not None
    assert task.status == TaskStatus.BLOCKED
    assert task.failure_code == "NEEDS_INFORMATION"
