from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "docs" / "DECISIONS_P0.md"

REQUIRED_FIELDS = [
    "Final decision",
    "Decision rationale",
    "Impact modules",
    "P0 acceptance rule",
    "Change process",
    "Current status",
    "External dependencies",
]


def _section_for_oq(text: str, oq_id: str) -> str:
    pattern = re.compile(
        rf"^### {oq_id}\b(?P<body>.*?)(?=^### OQ-\d{{2}}\b|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"{oq_id} decision section is missing"
    return match.group("body")


def test_T000_all_OQ_have_decision_and_owner() -> None:
    text = DECISIONS.read_text(encoding="utf-8")

    for number in range(1, 21):
        oq_id = f"OQ-{number:02d}"
        assert len(re.findall(rf"^### {oq_id}\b", text, re.MULTILINE)) == 1, (
            f"{oq_id} must appear exactly once as a level-3 decision heading"
        )
        section = _section_for_oq(text, oq_id)
        for field in REQUIRED_FIELDS:
            assert f"- **{field}**:" in section, f"{oq_id} is missing field: {field}"

    assert "`SE-Mentor`" in text
    assert "`se_mentor`" in text
    assert "`se-mentor`" in text
    assert "Bootstrap TDD exception" in text
