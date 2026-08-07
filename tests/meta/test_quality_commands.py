from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_all


def test_T003_uses_current_python_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, cwd: Path) -> int:
        calls.append((command, cwd))
        return 0

    monkeypatch.setattr(check_all, "preflight", lambda: 0)
    monkeypatch.setattr(check_all, "run", fake_run)

    assert check_all.main() == 0

    python_commands = [command for command, _cwd in calls[:4]]
    assert python_commands
    assert all(command[0] == sys.executable for command in python_commands)
    assert all(command[0] != "python" for command in python_commands)


def test_T003_propagates_child_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], *, cwd: Path) -> int:
        if command[:3] == [sys.executable, "-m", "mypy"]:
            return 17
        return 0

    monkeypatch.setattr(check_all, "preflight", lambda: 0)
    monkeypatch.setattr(check_all, "run", fake_run)

    assert check_all.main() == 17


def test_T003_uses_frontend_working_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, cwd: Path) -> int:
        calls.append((command, cwd))
        return 0

    monkeypatch.setattr(check_all, "preflight", lambda: 0)
    monkeypatch.setattr(check_all, "run", fake_run)

    assert check_all.main() == 0

    frontend_calls = [
        (command, cwd) for command, cwd in calls if command[0] == check_all.NPM
    ]
    assert frontend_calls
    assert all(cwd == check_all.ROOT / "frontend" for _command, cwd in frontend_calls)
    if sys.platform == "win32":
        assert all(command[0] == "npm.cmd" for command, _cwd in frontend_calls)


def test_T003_reports_missing_python_tool_actionably(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[:3] == [sys.executable, "-m", "ruff"]:
            return subprocess.CompletedProcess(command, 1, "", "No module named ruff")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert check_all.preflight() == 1
    output = capsys.readouterr().err
    assert "QUALITY_ENV_MISSING_PYTHON_TOOL" in output
    assert f"Current interpreter:\n{sys.executable}" in output
    assert "Missing:\nruff" in output
    assert "Expected project interpreter:" in output
    assert "backend\\.venv\\Scripts\\python.exe scripts\\check_all.py" in output
