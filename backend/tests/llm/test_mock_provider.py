from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.base import LLMRequest, ProviderCancelled, ProviderTimeout
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.llm import LLMCall, LLMCallStatus


def test_T053_undefined_mock_call_fails_and_script_is_deterministic(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "mock-provider.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    provider = MockLLMProvider(
        model="mock-model",
        script=(
            MockResponse(match="proposal", content='{"ok": true}', input_tokens=5, output_tokens=3),
        ),
    )

    request = LLMRequest(prompt_summary="proposal request", input_text="make proposal")
    first = provider.complete(request)
    second = provider.reset().complete(request)

    assert first == second
    assert first.usage.input_tokens == 5
    assert first.usage.output_tokens == 3
    assert provider.calls == 1

    with pytest.raises(ProviderTimeout):
        MockLLMProvider(model="mock-model", script=(), timeout_after_calls=0).complete(request)
    with pytest.raises(ProviderCancelled):
        MockLLMProvider(model="mock-model", script=(), cancelled=True).complete(request)
    with pytest.raises(KeyError, match="undefined mock call"):
        provider.complete(LLMRequest(prompt_summary="unknown", input_text="unknown"))

    with session_scope(session_factory) as session:
        call = provider.record_usage(
            session,
            iteration_id=ids["iteration_id"],
            response=first,
            request_summary=request.prompt_summary,
        )
        call_id = call.id

    with session_scope(session_factory) as session:
        stored = session.get(LLMCall, call_id)
        assert stored is not None
        assert stored.provider_name == "mock"
        assert stored.model_name == "mock-model"
        assert stored.input_tokens == 5
        assert stored.output_tokens == 3
        assert stored.status == LLMCallStatus.SUCCESS
