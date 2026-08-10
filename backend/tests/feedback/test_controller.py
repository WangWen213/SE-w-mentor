from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.contracts.enums import FeedbackKind, FeedbackSeverity
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.feedback.controller import FeedbackController, FeedbackSource
from se_mentor.models.validation import FeedbackSignal


def test_T073_feedback_is_compact_actionable_and_secret_free(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "feedback.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    long_log = "\n".join(
        [
            "FAILED tests/test_api.py::test_contract",
            "AssertionError: expected 200 got 500",
            "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz",
            *[f"noise {index}" for index in range(200)],
        ]
    )

    with session_scope(session_factory) as session:
        signal = FeedbackController(session, max_chars=260).create(
            task_id=ids["task_id"],
            source=FeedbackSource(
                source_type="validation",
                category="CONTRACT_FAILURE",
                retryable=True,
                log_text=long_log,
                artifact_ref="artifact://logs/full.log",
            ),
        )
        stored = session.query(FeedbackSignal).one()

    assert signal.kind == FeedbackKind.VALIDATION
    assert signal.severity == FeedbackSeverity.ERROR
    assert len(signal.message) <= 260
    assert "tests/test_api.py::test_contract" in signal.message
    assert "CONTRACT_FAILURE" in signal.message
    assert "retryable" in signal.message
    assert "sk-proj" not in signal.message
    assert "[REDACTED:SECRET]" in signal.message
    assert stored.summary == signal.message
    assert "artifact://logs/full.log" in stored.evidence_json
