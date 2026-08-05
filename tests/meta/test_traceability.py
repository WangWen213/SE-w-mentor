from __future__ import annotations

from pathlib import Path

from scripts.check_traceability import REQUIRED_REQUIREMENTS, check_matrix


def test_T001_all_p0_requirements_have_task_test_evidence() -> None:
    result = check_matrix(Path("docs/TRACEABILITY_MATRIX.md"))

    assert result.ok, result.message
    assert "US-01-AC-01" in REQUIRED_REQUIREMENTS
    assert "FR-12-03" in REQUIRED_REQUIREMENTS
    assert "NFR-OBS-11" in REQUIRED_REQUIREMENTS
    assert "AC-OBS" in REQUIRED_REQUIREMENTS
    assert len(REQUIRED_REQUIREMENTS) == 134


def test_T001_missing_mapping_returns_nonzero(tmp_path: Path) -> None:
    matrix = tmp_path / "TRACEABILITY_MATRIX.md"
    matrix.write_text(
        "| requirement | priority | primary task | supporting task | test | evidence | status |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| US-01-AC-01 | P0 | T025#US-01-AC-01 | T001 | "
        "`tests/example.py` | `evidence/tdd/T025.md` | draft |",
        encoding="utf-8",
    )

    result = check_matrix(matrix)

    assert not result.ok
    assert "missing" in result.message


def test_T001_duplicate_primary_task_returns_nonzero(tmp_path: Path) -> None:
    lines = [
        "| requirement | priority | primary task | supporting task | test | evidence | status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for requirement in REQUIRED_REQUIREMENTS:
        task = "T999" if requirement in {"US-01-AC-01", "US-01-AC-02"} else f"T{len(lines):03d}"
        lines.append(
            f"| {requirement} | P0 | {task} | T001 | `tests/{requirement}.py` | "
            f"`evidence/tdd/{requirement}.md` | draft |"
        )
    matrix = tmp_path / "TRACEABILITY_MATRIX.md"
    matrix.write_text("\n".join(lines), encoding="utf-8")

    result = check_matrix(matrix)

    assert not result.ok
    assert "duplicate primary task" in result.message
