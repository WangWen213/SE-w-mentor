from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.contracts.enums import EventType
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.validation import ProgressEvent
from se_mentor.progress.monitor import ProgressMonitor, ProgressSignal


def test_T068_rephrased_same_plan_is_not_progress_but_new_evidence_is(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "progress.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        monitor = ProgressMonitor(session)
        rephrased = monitor.evaluate(
            task_id=ids["task_id"],
            before=ProgressSignal(plan="fix login bug", evidence_refs=(), failing_tests=3),
            after=ProgressSignal(plan="repair the login defect", evidence_refs=(), failing_tests=3),
        )
        improved = monitor.evaluate(
            task_id=ids["task_id"],
            before=ProgressSignal(
                plan="fix login bug", evidence_refs=("log:red",), failing_tests=3
            ),
            after=ProgressSignal(
                plan="fix login bug",
                evidence_refs=("log:red", "log:green"),
                failing_tests=1,
            ),
        )
        events = session.query(ProgressEvent).all()

    assert rephrased.progress is False
    assert "rephrasing" in rephrased.reason
    assert improved.progress is True
    assert improved.score > rephrased.score
    assert len(events) == 2
    assert events[0].event_type == EventType.TOOL_EXECUTED
    assert "new evidence" in events[1].summary
