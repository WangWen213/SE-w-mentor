from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import check_all

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_alembic_heads.py"
POLICY = ROOT / "docs" / "MIGRATION_POLICY.md"


def test_T008_current_repository_has_exactly_one_head() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_T008_dual_head_fixture_fails_closed(tmp_path: Path) -> None:
    _write_alembic_fixture(
        tmp_path,
        [
            ("0001_base", None),
            ("0100_project_a", "0001_base"),
            ("0101_project_b", "0001_base"),
        ],
    )

    result = _run_checker(tmp_path)

    output = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode != 0
    assert "detected head count: 2" in output
    assert "multiple alembic heads" in output
    assert "0100_project_a" in output
    assert "0101_project_b" in output


def test_T008_zero_head_fixture_fails_closed(tmp_path: Path) -> None:
    _write_alembic_fixture(tmp_path, [])

    result = _run_checker(tmp_path)

    output = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode != 0
    assert "detected head count: 0" in output
    assert "no alembic heads" in output


def test_T008_policy_documents_migration_ownership_contract() -> None:
    policy = POLICY.read_text(encoding="utf-8").lower()

    required_fragments = [
        "schema/migration owner only",
        "wt-schema",
        "shared/high-conflict resource",
        "must not create formal alembic revisions",
        "revision allocation",
        "rebase/regenerate",
        "fail closed",
        "later schema tasks",
    ]

    for fragment in required_fragments:
        assert fragment in policy


def test_T008_check_all_runs_single_head_gate(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(check_all, "preflight", lambda: 0)
    monkeypatch.setattr(check_all, "run", fake_run)

    assert check_all.main() == 0
    assert any(
        any(command_part.endswith("check_alembic_heads.py") for command_part in command)
        for command in calls
    )


def _run_checker(fixture_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--config",
            str(fixture_root / "alembic.ini"),
            "--cwd",
            str(fixture_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_alembic_fixture(
    fixture_root: Path,
    revisions: list[tuple[str, str | None]],
) -> None:
    migrations = fixture_root / "migrations"
    versions = migrations / "versions"
    versions.mkdir(parents=True)
    (fixture_root / "alembic.ini").write_text(
        "[alembic]\nscript_location = migrations\n",
        encoding="utf-8",
    )
    (migrations / "script.py.mako").write_text("", encoding="utf-8")

    for revision, down_revision in revisions:
        down_revision_literal = repr(down_revision)
        (versions / f"{revision}.py").write_text(
            "\n".join(
                [
                    f"revision = {revision!r}",
                    f"down_revision = {down_revision_literal}",
                    "branch_labels = None",
                    "depends_on = None",
                    "",
                    "def upgrade() -> None:",
                    "    pass",
                    "",
                    "def downgrade() -> None:",
                    "    pass",
                    "",
                ]
            ),
            encoding="utf-8",
        )
