from __future__ import annotations

from pathlib import Path

from scripts.check_traceability import REQUIRED_REQUIREMENTS, check_matrix

HEADER = (
    "| requirement | requirement anchor | priority | primary task | supporting tasks | "
    "test | evidence | status |"
)
DIVIDER = "| --- | --- | --- | --- | --- | --- | --- | --- |"


def _matrix_with_rows(tmp_path: Path, rows: list[str]) -> Path:
    matrix = tmp_path / "TRACEABILITY_MATRIX.md"
    matrix.write_text("\n".join([HEADER, DIVIDER, *rows]), encoding="utf-8")
    return matrix


def _valid_planned_row(requirement: str, task: str = "T025") -> str:
    return (
        f"| {requirement} | {requirement} | P0 | {task} | T001 | "
        f"`tests/planned/{requirement}.py` | `evidence/tdd/{task}.md` | planned |"
    )


def test_T001_all_p0_requirements_have_task_test_evidence() -> None:
    result = check_matrix(Path("docs/TRACEABILITY_MATRIX.md"))

    assert result.ok, result.message
    assert "US-01-AC-01" in REQUIRED_REQUIREMENTS
    assert "FR-12-03" in REQUIRED_REQUIREMENTS
    assert "NFR-OBS-11" in REQUIRED_REQUIREMENTS
    assert "AC-OBS" in REQUIRED_REQUIREMENTS
    assert len(REQUIRED_REQUIREMENTS) == 134


def test_T001_rejects_pseudo_primary_task_ids(tmp_path: Path) -> None:
    matrix = _matrix_with_rows(
        tmp_path,
        [_valid_planned_row("US-01-AC-01", task="T025#US-01-AC-01")],
    )

    result = check_matrix(matrix)

    assert not result.ok
    assert "invalid primary task" in result.message


def test_T001_rejects_duplicate_requirement_primary_rows(tmp_path: Path) -> None:
    matrix = _matrix_with_rows(
        tmp_path,
        [
            _valid_planned_row("US-01-AC-01", task="T025"),
            _valid_planned_row("US-01-AC-01", task="T026"),
        ],
    )

    result = check_matrix(matrix)

    assert not result.ok
    assert "duplicate requirement anchor" in result.message


def test_T001_rejects_invalid_status(tmp_path: Path) -> None:
    matrix = _matrix_with_rows(
        tmp_path,
        [
            (
                "| US-01-AC-01 | US-01-AC-01 | P0 | T025 | T001 | "
                "`tests/planned/US-01-AC-01.py` | `evidence/tdd/T025.md` | draft |"
            )
        ],
    )

    result = check_matrix(matrix)

    assert not result.ok
    assert "invalid status" in result.message


def test_T001_planned_rows_allow_future_paths(tmp_path: Path) -> None:
    rows = [
        _valid_planned_row(requirement, task="T025")
        for requirement in REQUIRED_REQUIREMENTS
    ]
    matrix = _matrix_with_rows(tmp_path, rows)

    result = check_matrix(matrix)

    assert result.ok, result.message


def test_T001_verified_rows_require_existing_test_and_evidence(tmp_path: Path) -> None:
    rows = [
        _valid_planned_row(requirement, task="T025").replace("planned |", "verified |")
        for requirement in REQUIRED_REQUIREMENTS
    ]
    matrix = _matrix_with_rows(tmp_path, rows)

    result = check_matrix(matrix)

    assert not result.ok
    assert "verified" in result.message
    assert "does not exist" in result.message


def test_T115_release_gate_requires_all_p0_requirements_verified(
    tmp_path: Path,
) -> None:
    rows = [
        _valid_planned_row(requirement, task="T115")
        for requirement in REQUIRED_REQUIREMENTS
    ]
    matrix = _matrix_with_rows(tmp_path, rows)

    result = check_matrix(matrix, release_gate=True)

    assert not result.ok
    assert "release gate requires verified P0 requirements" in result.message


def test_T001_missing_mapping_returns_nonzero(tmp_path: Path) -> None:
    matrix = _matrix_with_rows(
        tmp_path,
        [
            (
                "| US-01-AC-01 | US-01-AC-01 | P0 | T025 | T001 | "
                "`tests/example.py` | `evidence/tdd/T025.md` | planned |"
            )
        ],
    )

    result = check_matrix(matrix)

    assert not result.ok
    assert "missing" in result.message


def test_T001_duplicate_primary_task_returns_nonzero(tmp_path: Path) -> None:
    rows = [
        _valid_planned_row(requirement, task="T025")
        for requirement in REQUIRED_REQUIREMENTS
    ]
    matrix = _matrix_with_rows(tmp_path, rows)

    result = check_matrix(matrix)

    assert result.ok, result.message
