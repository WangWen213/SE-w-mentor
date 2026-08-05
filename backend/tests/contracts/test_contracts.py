from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from se_mentor.contracts.actions import AgentActionAdapter
from se_mentor.contracts.enums import ActionType, TrustLevel
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
                "reason": "inspect",
                "path": "README.md",
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
