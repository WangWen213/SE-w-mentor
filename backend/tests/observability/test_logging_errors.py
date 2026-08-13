from __future__ import annotations

import logging

from se_mentor.core.error_mapper import ErrorMapper, SideEffectState
from se_mentor.observability.logging import (
    LogCategory,
    StructuredLogEvent,
    StructuredLogger,
    configure_runtime_logging,
)


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


def test_perf_runtime_logging_writes_perf_lines_once(tmp_path) -> None:
    logger = logging.getLogger("se_mentor")
    before_handlers = list(logger.handlers)
    before_level = logger.level
    before_propagate = logger.propagate
    try:
        log_path = configure_runtime_logging(tmp_path)
        configure_runtime_logging(tmp_path)

        perf_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
            and getattr(handler, "baseFilename", None) == str(log_path)
        ]
        logging.getLogger("se_mentor.tests").info("[perf] test.stage duration_ms=%s", 7)
        logging.getLogger("se_mentor.tests").info("ordinary application log")
        for handler in perf_handlers:
            handler.flush()

        assert len(perf_handlers) == 1
        assert log_path.name == "perf-runtime.log"
        text = log_path.read_text(encoding="utf-8")
        assert "[perf] test.stage duration_ms=7" in text
        assert "ordinary application log" not in text
    finally:
        for handler in list(logger.handlers):
            if handler not in before_handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.handlers[:] = before_handlers
        logger.setLevel(before_level)
        logger.propagate = before_propagate
