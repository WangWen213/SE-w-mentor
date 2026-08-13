from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.api.events import BUS
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.execution.orchestrator import ExecutionOrchestrator
from se_mentor.llm.base import LLMRequest, LLMResponse, LLMUsage
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import FileChange
from se_mentor.models.task import ChangeTask, TaskStatus


def test_execution_without_real_file_change_fails_terminally(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "execution.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=None,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["app.py"]',
            write_paths_json='["app.py"]',
            protected_paths_json="[]",
            commands_json='["RUN_COMMAND"]',
            network_json="{}",
            resource_limits_json="{}",
            invalidation_json="{}",
            evidence_json="{}",
        )
        session.add(policy)
        session.flush()
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.active_policy_id = policy.id

    result = ExecutionOrchestrator(session_factory, runtime=NoChangeRuntime()).execute_task(
        ids["task_id"],
        command="RUN_COMMAND",
    )

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.failure_code == "NO_CODE_CHANGE_PRODUCED"
        assert task.failure_message == "execution completed without real file changes"
    assert result.status == "FAILED"
    assert not any(
        event.event_type == "FILE_CHANGED" for event in BUS.replay(task_id=ids["task_id"])
    )


def test_execution_dispatches_agent_loop_to_real_file_change(tmp_path: Path, monkeypatch) -> None:
    engine = create_schema(tmp_path / "execution.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    session_factory = create_session_factory(engine)
    provider = TwoStepProvider()
    with session_scope(session_factory) as session:
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=None,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["app.py"]',
            write_paths_json='["app.py"]',
            protected_paths_json="[]",
            commands_json='["RUN_COMMAND"]',
            network_json="{}",
            resource_limits_json="{}",
            invalidation_json="{}",
            evidence_json="{}",
        )
        session.add(policy)
        session.flush()
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        task.active_policy_id = policy.id
        task.status = TaskStatus.ACTION_PENDING

    result = ExecutionOrchestrator(session_factory, provider_override=provider).execute_task(
        ids["task_id"],
        command="RUN_COMMAND",
    )

    assert result.status == "COMPLETED"
    assert target.read_text(encoding="utf-8") == "value = 2\n"
    assert len(provider.requests) == 2
    assert provider.requests[0].response_schema is not None
    assert "Previous tool result" in provider.requests[1].input_text
    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        changes = session.query(FileChange).filter_by(task_id=ids["task_id"]).all()
        assert [change.relative_path for change in changes] == ["app.py"]
    event_types = [event.event_type for event in BUS.replay(task_id=ids["task_id"])]
    assert "EXECUTION_STARTED" in event_types
    assert "ACTION_STARTED" in event_types
    assert "ACTION_COMPLETED" in event_types
    assert "FILE_CHANGED" in event_types
    assert "EXECUTION_COMPLETED" in event_types


class NoChangeRuntime:
    def run_task(self, **_kwargs) -> None:
        return None


class TwoStepProvider:
    provider_name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            content = {
                "action_type": "READ_FILE",
                "parameters": {"path": "app.py", "start_line": 1, "end_line": 20},
                "reason": "inspect current file",
            }
        else:
            content = {
                "action_type": "APPLY_PATCH",
                "parameters": {
                    "relative_path": "app.py",
                    "replacements": [{"old": "value = 1", "new": "value = 2"}],
                },
                "reason": "apply confirmed edit",
            }
        return LLMResponse(
            content=json.dumps(content),
            usage=LLMUsage(input_tokens=10, output_tokens=10),
            model=self.model,
            provider=self.provider_name,
        )
