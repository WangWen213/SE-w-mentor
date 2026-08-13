from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.agent.repair_loop import RepairAttempt, RepairLoop
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.task import ChangeTask


def test_T076_first_patch_fails_second_patch_passes_with_two_distinct_diffs(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "repair.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        loop = RepairLoop(session, max_repairs=3)
        first = loop.record_attempt(
            task_id=ids["task_id"],
            attempt=RepairAttempt(diff_hash="aaa", failure_signature="test_x failed", passed=False),
        )
        second = loop.record_attempt(
            task_id=ids["task_id"],
            attempt=RepairAttempt(diff_hash="bbb", failure_signature="", passed=True),
        )
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None

    assert first.continue_repair is True
    assert second.completed is True
    assert second.distinct_diffs == 2
    assert task.repair_count == 2
