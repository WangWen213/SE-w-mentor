from __future__ import annotations

from pathlib import Path

REPORT = Path("evidence/logs/T114/cold-start-first-pass.md")


def test_T114_first_cold_start_report_records_foundation_pass() -> None:
    assert REPORT.exists(), "T114 first cold-start report is missing"

    report = REPORT.read_text(encoding="utf-8")
    required_fragments = [
        "Status: PASS",
        "T000-T008 complete",
        "decision freeze coherent",
        "traceability coherent",
        "shared contracts coherent",
        "migration ownership coherent",
        "single Alembic head",
        "T009 NOT STARTED",
    ]

    for fragment in required_fragments:
        assert fragment in report
