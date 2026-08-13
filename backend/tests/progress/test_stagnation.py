from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.audit import AlertEvent, AlertSeverity
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.progress.stagnation import ActionObservation, StagnationMonitor


def test_AC_FR05_05_detects_semantic_stagnation(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "stagnation.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        monitor = StagnationMonitor(session, threshold=3, max_iterations=10, token_budget=100)
        first = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "a.py", progress=False, evidence_refs=()),
            provider_calls=1,
            spent_tokens=5,
        )
        different_file = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "b.py", progress=False, evidence_refs=()),
            provider_calls=1,
            spent_tokens=5,
        )
        repeated = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "b.py", progress=False, evidence_refs=()),
            provider_calls=1,
            spent_tokens=5,
        )
        warning = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "b.py", progress=False, evidence_refs=()),
            provider_calls=1,
            spent_tokens=5,
        )
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        alerts = session.query(AlertEvent).all()

    assert first.stagnated is False
    assert different_file.stagnated is False
    assert repeated.stagnated is False
    assert warning.stagnated is True
    assert warning.provider_allowed is False
    assert task.status == TaskStatus.STAGNATION_WARNING
    assert alerts[-1].severity == AlertSeverity.WARNING
