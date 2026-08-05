from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = [
    "requirement",
    "priority",
    "primary task",
    "supporting task",
    "test",
    "evidence",
    "status",
]

US_ACCEPTANCE_COUNTS = {
    "US-01": 3,
    "US-02": 4,
    "US-03": 4,
    "US-04": 4,
    "US-05": 4,
    "US-06": 4,
}

FR_COUNTS = {
    "FR-01": 4,
    "FR-02": 4,
    "FR-03": 4,
    "FR-04": 5,
    "FR-05": 6,
    "FR-06": 5,
    "FR-07": 9,
    "FR-08": 7,
    "FR-09": 4,
    "FR-10": 3,
    "FR-11": 2,
    "FR-12": 3,
}

NFR_COUNTS = {
    "NFR-PERF": 7,
    "NFR-SEC": 10,
    "NFR-CRED": 10,
    "NFR-USA": 10,
    "NFR-OBS": 11,
}

AC_REQUIREMENTS = [
    "AC-FR",
    "AC-PERF",
    "AC-SEC",
    "AC-CRED",
    "AC-USA",
    "AC-OBS",
    "AC-CI",
]

REQUIRED_REQUIREMENTS = (
    [
        f"{story}-AC-{number:02d}"
        for story, count in US_ACCEPTANCE_COUNTS.items()
        for number in range(1, count + 1)
    ]
    + [
        f"{family}-{number:02d}"
        for family, count in FR_COUNTS.items()
        for number in range(1, count + 1)
    ]
    + [
        f"{family}-{number:02d}"
        for family, count in NFR_COUNTS.items()
        for number in range(1, count + 1)
    ]
    + AC_REQUIREMENTS
)


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


def _parse_table(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        rows.append(dict(zip(header, cells, strict=False)))
    if header != REQUIRED_COLUMNS:
        raise ValueError(f"matrix columns must be: {', '.join(REQUIRED_COLUMNS)}")
    return rows


def check_matrix(path: Path) -> CheckResult:
    try:
        rows = _parse_table(path)
    except (OSError, UnicodeError, ValueError) as exc:
        return CheckResult(False, str(exc))

    by_requirement = {row.get("requirement", ""): row for row in rows}
    missing = [requirement for requirement in REQUIRED_REQUIREMENTS if requirement not in by_requirement]
    if missing:
        return CheckResult(False, f"missing P0 requirement mapping: {', '.join(missing)}")

    seen_tasks: dict[str, str] = {}
    for requirement in REQUIRED_REQUIREMENTS:
        row = by_requirement[requirement]
        for field in ["primary task", "supporting task", "test", "evidence"]:
            if not row.get(field) or row[field].lower() == "pending":
                return CheckResult(False, f"{requirement} has empty {field}")
        for field in ["test", "evidence"]:
            if not row[field].startswith("`") or not row[field].endswith("`"):
                return CheckResult(False, f"{requirement} has invalid {field} path")
        task = row["primary task"]
        if task in seen_tasks:
            return CheckResult(
                False,
                f"duplicate primary task {task}: {seen_tasks[task]} and {requirement}",
            )
        seen_tasks[task] = requirement

    return CheckResult(True, f"{len(REQUIRED_REQUIREMENTS)} P0 requirements mapped")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/TRACEABILITY_MATRIX.md")
    result = check_matrix(path)
    if not result.ok:
        print(result.message, file=sys.stderr)
        return 1
    print(result.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
