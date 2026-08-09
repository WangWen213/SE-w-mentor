from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.contracts.enums import ToolStatus
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.tools.dispatcher import ToolDispatcher
from se_mentor.tools.registry import ToolRegistry, ToolSpec


def test_T057_unregistered_or_denied_tool_never_calls_handler(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "dispatcher.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(ToolSpec(name="write_file", risk="HIGH", timeout_seconds=30))

    with session_scope(session_factory) as session:
        dispatcher = ToolDispatcher(session, registry)
        missing = dispatcher.dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="missing",
            parameters={},
            enforcer=lambda: False,
            handler=lambda: calls.append("missing"),
        )
        denied = dispatcher.dispatch(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            tool_name="write_file",
            parameters={"path": "../outside.py"},
            enforcer=lambda: False,
            handler=lambda: calls.append("denied"),
        )

    assert missing.status == ToolStatus.BLOCKED
    assert missing.error_code == "UNREGISTERED_TOOL"
    assert denied.status == ToolStatus.BLOCKED
    assert denied.error_code == "POLICY_DENIED"
    assert calls == []
