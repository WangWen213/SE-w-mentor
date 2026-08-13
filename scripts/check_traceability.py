from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = [
    "requirement",
    "requirement anchor",
    "priority",
    "primary task",
    "supporting tasks",
    "test",
    "evidence",
    "status",
]

VALID_STATUSES = {"planned", "implemented", "verified", "blocked", "deferred-p1"}
TASK_RE = re.compile(r"^T\d{3}$")
PLAN_PATH = Path("SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md")

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


def _strip_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _parse_plan_task_ids(plan_path: Path = PLAN_PATH) -> set[str]:
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(re.findall(r"^## (T\d{3})\b", text, re.MULTILINE))


def _split_task_ids(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，]", value) if part.strip()]


def _valid_task(task_id: str, plan_tasks: set[str]) -> bool:
    return bool(TASK_RE.fullmatch(task_id)) and task_id in plan_tasks


def check_matrix(path: Path, *, release_gate: bool = False) -> CheckResult:
    try:
        rows = _parse_table(path)
    except (OSError, UnicodeError, ValueError) as exc:
        return CheckResult(False, str(exc))

    plan_tasks = _parse_plan_task_ids()
    if not plan_tasks:
        return CheckResult(False, f"cannot read PLAN task ids from {PLAN_PATH}")

    by_anchor: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=1):
        anchor = row.get("requirement anchor", "")
        if not anchor:
            return CheckResult(False, f"row {index} has empty requirement anchor")
        if anchor in by_anchor:
            return CheckResult(False, f"duplicate requirement anchor {anchor}")
        by_anchor[anchor] = row

        status = row.get("status", "")
        if status not in VALID_STATUSES:
            return CheckResult(False, f"{anchor} has invalid status {status}")

        for field in ["primary task", "supporting tasks", "test", "evidence"]:
            if not row.get(field) or row[field].lower() == "pending":
                return CheckResult(False, f"{anchor} has empty {field}")

        primary_task = row["primary task"]
        if not _valid_task(primary_task, plan_tasks):
            return CheckResult(
                False, f"{anchor} has invalid primary task {primary_task}"
            )

        for task in _split_task_ids(row["supporting tasks"]):
            if not _valid_task(task, plan_tasks):
                return CheckResult(
                    False, f"{anchor} has invalid supporting task {task}"
                )

        for field in ["test", "evidence"]:
            if not row[field].startswith("`") or not row[field].endswith("`"):
                return CheckResult(False, f"{anchor} has invalid {field} path")

        if status == "verified":
            for field in ["test", "evidence"]:
                target = Path(_strip_code(row[field]))
                if not target.exists():
                    return CheckResult(
                        False,
                        f"{anchor} verified {field} path does not exist: {target}",
                    )

    missing = [
        requirement
        for requirement in REQUIRED_REQUIREMENTS
        if requirement not in by_anchor
    ]
    if missing:
        return CheckResult(
            False, f"missing P0 requirement mapping: {', '.join(missing)}"
        )

    if release_gate:
        not_verified = [
            requirement
            for requirement in REQUIRED_REQUIREMENTS
            if by_anchor[requirement].get("status") != "verified"
        ]
        if not_verified:
            return CheckResult(
                False,
                "release gate requires verified P0 requirements: "
                + ", ".join(not_verified),
            )

    return CheckResult(True, f"{len(REQUIRED_REQUIREMENTS)} P0 requirements mapped")


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--release-gate"]
    path = Path(args[0]) if args else Path("docs/TRACEABILITY_MATRIX.md")
    result = check_matrix(path, release_gate="--release-gate" in sys.argv[1:])
    if not result.ok:
        print(result.message, file=sys.stderr)
        return 1
    print(result.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
