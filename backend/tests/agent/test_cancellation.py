from __future__ import annotations

import sys
from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.agent.runtime import AgentRuntime, CancellationRequested
from se_mentor.context.context_builder import ContextBuilder
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.tools.registry import ToolRegistry


def test_T067_cancel_stops_future_llm_calls_and_reaches_safe_state(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "cancel.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    provider = MockLLMProvider(
        model="mock-model",
        script=(
            MockResponse(
                match="run",
                content='{"action_type":"READ_FILE","path":"app.py","reason":"inspect"}',
                input_tokens=1,
                output_tokens=1,
            ),
        ),
    )
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        runner = SingleTurnAgentRunner(
            session,
            project_root=repo,
            context_builder=ContextBuilder(max_chars=2000),
            provider=provider,
            registry=ToolRegistry(),
            tool_handlers={},
        )
        runtime = AgentRuntime(session, runner=runner)
        runtime.request_cancel(task_id=ids["task_id"], reason="user stop")
        result = runtime.run_once(
            task_id=ids["task_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            goal="run",
        )
        task = session.get(ChangeTask, ids["task_id"])

    assert result.cancelled is True
    assert result.safe_state == "CANCELLED_BEFORE_LLM"
    assert result.next_options == ("retain_changes", "rollback")
    assert provider.calls == 0
    assert task.status == TaskStatus.CANCELLED

    runtime = AgentRuntime()
    process = runtime.start_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
    )
    runtime.request_cancel(task_id=ids["task_id"], reason="stop child")
    assert runtime.terminate_children(timeout_seconds=5) == 1
    assert process.poll() is not None

    token = runtime.cancellation_token(ids["task_id"])
    with token.atomic_write_section():
        token.cancel("during replace")
        token.raise_if_cancelled()
    with pytest.raises(CancellationRequested):
        token.raise_if_cancelled()
