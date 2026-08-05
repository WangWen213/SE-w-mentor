from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = ["requirement", "priority", "task", "test", "evidence", "status"]

REQUIRED_REQUIREMENTS = [
    "US-01",
    "US-02",
    "US-03",
    "US-04",
    "US-05",
    "US-06",
    "FR-01",
    "FR-02",
    "FR-03",
    "FR-04",
    "FR-05",
    "FR-06",
    "FR-07",
    "FR-08",
    "FR-09",
    "FR-10",
    "FR-11",
    "FR-12",
    "NFR-PERF",
    "NFR-SEC",
    "NFR-CRED",
    "NFR-USA",
    "NFR-OBS",
    "AC-FR",
    "AC-PERF",
    "AC-SEC",
    "AC-CRED",
    "AC-USA",
    "AC-OBS",
    "AC-CI",
]


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
        for field in ["task", "test", "evidence"]:
            if not row.get(field) or row[field].lower() == "pending":
                return CheckResult(False, f"{requirement} has empty {field}")
        task = row["task"]
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
