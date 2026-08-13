from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.evaluation.service import EvaluationService
from se_mentor.models.evaluation import TaskEvaluation
from se_mentor.models.execution import (
    FileChange,
    FileChangeType,
    ToolExecution,
    ToolExecutionStatus,
)
from se_mentor.models.knowledge import EngineeringKnowledge
from se_mentor.models.task import ChangeTask, TaskStatus


def test_task_evaluation_persists_projection_and_memory_idempotently(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "evaluation.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.status = TaskStatus.COMPLETED
        tool = ToolExecution(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="APPLY_PATCH",
            command_summary="apply patch app.py",
            status=ToolExecutionStatus.SUCCEEDED,
            evidence_json=json.dumps({"relative_path": "app.py"}),
        )
        session.add(tool)
        session.flush()
        session.add(
            FileChange(
                task_id=ids["task_id"],
                tool_execution_id=tool.id,
                action_id=ids["action_id"],
                change_type=FileChangeType.MODIFY,
                relative_path="app.py",
                before_hash="a" * 64,
                after_hash="b" * 64,
            )
        )
        service = EvaluationService(session)
        first = service.persist_for_task(ids["task_id"])
        second = service.persist_for_task(ids["task_id"])

        evaluations = session.query(TaskEvaluation).all()
        memories = (
            session.query(EngineeringKnowledge)
            .filter(EngineeringKnowledge.knowledge_key == f"task-evaluation:{ids['task_id']}")
            .all()
        )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert len(evaluations) == 1
    assert len(memories) == 1
    payload = json.loads(evaluations[0].summary_json)
    assert payload["taskId"] == ids["task_id"]
    assert payload["hasEvaluation"] is True
    assert "app.py" in payload["execution"]["changedFiles"]
