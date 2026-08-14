from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.context.context_builder import ContextBuilder
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.governance import GovernanceDecision
from se_mentor.models.llm import AgentAction, LLMCall
from se_mentor.models.task import TaskIteration
from se_mentor.tools.registry import ToolRegistry, ToolSpec


def test_T066_read_action_flows_through_context_llm_parser_governance_dispatcher(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "iteration.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("answer = 42\n", encoding="utf-8")
    provider = MockLLMProvider(
        model="mock-model",
        script=(
            MockResponse(
                match="read app",
                content=(
                    '{"action_type":"READ_FILE",'
                    '"parameters":{"path":"app.py","start_line":1,"end_line":20},'
                    '"reason":"inspect"}'
                ),
                input_tokens=12,
                output_tokens=8,
            ),
        ),
    )
    registry = ToolRegistry()
    registry.register(ToolSpec("READ_FILE", "read", 10))
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        runner = SingleTurnAgentRunner(
            session,
            project_root=repo,
            context_builder=ContextBuilder(max_chars=2000),
            provider=provider,
            registry=registry,
            tool_handlers={
                "READ_FILE": lambda action: "".join(
                    (repo / action.parameters.path)
                    .read_text(encoding="utf-8")
                    .splitlines(keepends=True)[
                        action.parameters.start_line - 1 : action.parameters.end_line
                    ]
                )
            },
        )
        result = runner.run(
            task_id=ids["task_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            goal="read app",
        )
        iterations = session.query(TaskIteration).all()
        calls = session.query(LLMCall).all()
        actions = session.query(AgentAction).all()
        decisions = session.query(GovernanceDecision).all()

    assert result.tool_result is not None
    assert result.tool_result.value == "answer = 42\n"
    assert provider.calls == 1
    assert len(iterations) == 2
    assert len(calls) == 1
    assert len(actions) == 2
    assert len(decisions) == 3
    assert actions[-1].llm_call_id == calls[0].id
    assert decisions[-1].action_id == actions[-1].id
