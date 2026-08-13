from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from se_mentor.contracts.actions import AgentActionAdapter
from se_mentor.contracts.enums import (
    ActionType,
    FeedbackKind,
    FeedbackSeverity,
    StableErrorCode,
    ToolStatus,
    TrustLevel,
)
from se_mentor.contracts.errors import StableError
from se_mentor.contracts.evidence import EvidenceRef
from se_mentor.contracts.feedback import FeedbackSignal
from se_mentor.contracts.results import ToolResult

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def test_T004_unknown_action_and_extra_field_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentActionAdapter.validate_python({"action_type": "UNKNOWN", "reason": "bad"})

    with pytest.raises(ValidationError):
        AgentActionAdapter.validate_python(
            {
                "action_type": "READ_FILE",
                "parameters": {"path": "README.md", "start_line": 1, "end_line": 20},
                "reason": "inspect",
                "skip_governance": True,
            }
        )

    with pytest.raises(ValidationError):
        EvidenceRef(
            source="README.md",
            trust_level="trusted",  # type: ignore[arg-type]
            summary="case-sensitive enum should fail",
        )


def test_T004_contracts_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"status": "OK", "summary": "done", "unexpected": True})

    with pytest.raises(ValidationError):
        FeedbackSignal.model_validate(
            {"kind": "VALIDATION", "severity": "INFO", "message": "ok", "extra": True}
        )


def test_T004_schema_snapshots_match() -> None:
    action_schema = AgentActionAdapter.json_schema()
    result_schema = ToolResult.model_json_schema()

    action_snapshot = (SNAPSHOT_DIR / "agent_action_schema.json").read_text(encoding="utf-8")
    result_snapshot = (SNAPSHOT_DIR / "tool_result_schema.json").read_text(encoding="utf-8")

    assert json.loads(action_snapshot) == action_schema
    assert json.loads(result_snapshot) == result_schema
    assert ActionType.READ_FILE == "READ_FILE"
    assert TrustLevel.REPOSITORY_CONTENT == "REPOSITORY_CONTENT"


def test_T004_all_action_variants_validate() -> None:
    actions = [
        {
            "action_type": "READ_FILE",
            "parameters": {"path": "README.md", "start_line": 1, "end_line": 20},
            "reason": "inspect",
        },
        {"action_type": "SEARCH_CODE", "parameters": {"query": "create_app"}, "reason": "find"},
        {
            "action_type": "APPLY_PATCH",
            "parameters": {"relative_path": "x.txt", "replacements": [{"old": "x", "new": "y"}]},
            "reason": "edit",
        },
        {
            "action_type": "CREATE_FILE",
            "parameters": {"path": "x.txt", "content": "x"},
            "reason": "add",
        },
        {"action_type": "DELETE_FILE", "parameters": {"path": "x.txt"}, "reason": "remove"},
        {
            "action_type": "RUN_COMMAND",
            "parameters": {"program": "pytest", "args": ["-q"]},
            "reason": "verify",
        },
    ]

    for action in actions:
        assert AgentActionAdapter.validate_python(action)


def test_T004_round_trip_contracts_and_error_codes() -> None:
    evidence = EvidenceRef(
        source="README.md",
        trust_level=TrustLevel.REPOSITORY_CONTENT,
        summary="readme evidence",
        uri="file://README.md",
    )
    evidence_round_trip = EvidenceRef.model_validate_json(evidence.model_dump_json())
    assert evidence_round_trip == evidence

    result = ToolResult(status=ToolStatus.OK, summary="done", evidence=[evidence])
    result_round_trip = ToolResult.model_validate_json(result.model_dump_json())
    assert result_round_trip == result

    feedback = FeedbackSignal(
        kind=FeedbackKind.VALIDATION,
        severity=FeedbackSeverity.INFO,
        message="ok",
        evidence=evidence,
    )
    feedback_round_trip = FeedbackSignal.model_validate_json(feedback.model_dump_json())
    assert feedback_round_trip == feedback

    error = StableError(code=StableErrorCode.UNKNOWN_ACTION, message="unknown action")
    error_round_trip = StableError.model_validate_json(error.model_dump_json())
    assert error_round_trip == error


def test_T004_snapshot_drift_is_detectable() -> None:
    action_schema = AgentActionAdapter.json_schema()
    action_snapshot = json.loads(
        (SNAPSHOT_DIR / "agent_action_schema.json").read_text(encoding="utf-8")
    )

    drifted_schema = {**action_schema, "title": "DriftedAgentAction"}

    assert action_snapshot == action_schema
    assert action_snapshot != drifted_schema


def test_T004_frontend_and_backend_enums_are_consistent() -> None:
    frontend_enums = (
        Path(__file__).parents[3] / "frontend" / "src" / "contracts" / "enums.ts"
    ).read_text(encoding="utf-8")

    for action_type in ActionType:
        assert f'"{action_type.value}"' in frontend_enums
    for trust_level in TrustLevel:
        assert f'"{trust_level.value}"' in frontend_enums
