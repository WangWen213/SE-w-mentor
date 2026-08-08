from __future__ import annotations

from se_mentor.agent.action_parser import AgentActionParser, ParseOutcome
from se_mentor.contracts.enums import ActionType, FeedbackKind


def test_T056_free_text_shell_unknown_action_and_extra_fields_are_rejected() -> None:
    parser = AgentActionParser(project_root="C:/repo")

    valid = parser.parse(
        {
            "action_type": "READ_FILE",
            "path": "src/app.py",
            "reason": "inspect",
        }
    )
    unknown = parser.parse({"action_type": "FLY_TO_MOON", "reason": "bad"})
    extra = parser.parse(
        {
            "action_type": "READ_FILE",
            "path": "src/app.py",
            "reason": "inspect",
            "extra": "nope",
        }
    )
    free_shell = parser.parse(
        {
            "action_type": "RUN_COMMAND",
            "program": "bash",
            "args": ["-lc", "rm -rf src"],
            "reason": "bad",
        }
    )
    invalid_path = parser.parse(
        {
            "action_type": "DELETE_FILE",
            "path": "../outside.py",
            "reason": "bad",
        }
    )
    nested = parser.parse(
        {
            "action_type": "CREATE_FILE",
            "path": "src/app.py",
            "content": "ok",
            "reason": "bad",
            "metadata": {"action_type": "RUN_COMMAND"},
        }
    )

    assert valid.outcome is ParseOutcome.ACCEPTED
    assert valid.action is not None
    assert valid.action.action_type is ActionType.READ_FILE
    for result in (unknown, extra, free_shell, invalid_path, nested):
        assert result.outcome is ParseOutcome.REJECTED
        assert result.feedback is not None
        assert result.feedback.kind is FeedbackKind.TOOL
        assert result.action is None
