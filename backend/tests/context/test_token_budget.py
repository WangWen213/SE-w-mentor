from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.context.context_builder import ContextBuilder, ContextItem, TrustLabel
from se_mentor.context.token_budget import BudgetedLLMProvider, TokenBudgetPaused
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.base import LLMRequest
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.task import ChangeTask, TaskStatus


def test_AC_FR03_03_over_budget_pauses_before_provider_call(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "token-budget.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    context = ContextBuilder(max_chars=10_000).build(
        goal="Fix audit logging",
        governance_items=(
            ContextItem("deny", "governance", "DENY_HARD .env writes", 100, TrustLabel.SYSTEM),
        ),
        execution_policy=ContextItem(
            "policy",
            "policy",
            '{"write_paths":["backend/src/app/audit.py"]}',
            95,
            TrustLabel.SYSTEM,
        ),
        current_error=ContextItem(
            "error",
            "feedback",
            "pytest failed " * 400,
            90,
            TrustLabel.TOOL_OUTPUT,
        ),
        repository_items=(),
        knowledge_items=(),
    )
    provider = MockLLMProvider(
        model="mock",
        script=(
            MockResponse(match="audit", content='{"ok":true}', input_tokens=1, output_tokens=1),
        ),
    )

    with session_scope(session_factory) as session:
        gate = BudgetedLLMProvider(session, provider)
        with pytest.raises(TokenBudgetPaused):
            gate.complete(
                task_id=ids["task_id"],
                context_package=context,
                request=LLMRequest(prompt_summary="audit", input_text="audit"),
                max_total_tokens=64,
                reserved_output_tokens=16,
                safety_margin_tokens=8,
            )
        task = session.get(ChangeTask, ids["task_id"])

    assert provider.calls == 0
    assert task is not None
    assert task.status == TaskStatus.PAUSED
    assert task.failure_code == "TOKEN_BUDGET_EXCEEDED"
