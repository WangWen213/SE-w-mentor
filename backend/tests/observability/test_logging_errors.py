from __future__ import annotations

from se_mentor.core.error_mapper import ErrorMapper, SideEffectState
from se_mentor.observability.logging import LogCategory, StructuredLogEvent, StructuredLogger


def test_T100_error_reports_side_effect_state_without_secret_and_all_logs_correlate() -> None:
    logger = StructuredLogger()
    event = logger.emit(
        StructuredLogEvent(
            task_id="task-1",
            correlation_id="corr-1",
            category=LogCategory.TOOL,
            level="ERROR",
            message="tool failed with sk-proj-abcdefghijklmnop and long prompt",
            payload={"prompt": "x" * 5000, "path": "app.py"},
        )
    )
    error = ErrorMapper().map(
        code="TOOL_EXCEPTION",
        message="failed with sk-proj-abcdefghijklmnop",
        side_effect_state=SideEffectState.PARTIAL_CHANGES,
        task_id="task-1",
        correlation_id="corr-1",
    )

    assert event.task_id == "task-1"
    assert event.correlation_id == "corr-1"
    assert event.category == LogCategory.TOOL
    assert "sk-proj" not in event.message
    assert "sk-proj" not in error.message
    assert len(event.payload["prompt"]) < 700
    assert error.code == "TOOL_EXCEPTION"
    assert error.side_effect_state == SideEffectState.PARTIAL_CHANGES
    assert error.next_steps == ("inspect evidence", "retain changes", "rollback")
