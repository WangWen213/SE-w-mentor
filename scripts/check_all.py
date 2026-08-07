from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"
TMP = ROOT / ".tmp" / "check-all"
EXPECTED_PROJECT_INTERPRETER = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
PYTHON_TOOLS = ("ruff", "mypy", "pytest")
NODE_TOOLS = (("node", "--version"), (NPM, "--version"))


def run(command: list[str], *, cwd: Path) -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TMP)
    env["TEMP"] = str(TMP)
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


def preflight() -> int:
    missing_python_tools = [
        tool
        for tool in PYTHON_TOOLS
        if _probe([sys.executable, "-m", tool, "--version"], cwd=ROOT / "backend") != 0
    ]
    missing_node_tools = [
        command[0]
        for command in NODE_TOOLS
        if _probe(list(command), cwd=ROOT / "frontend") != 0
    ]
    if not missing_python_tools and not missing_node_tools:
        return 0

    if missing_python_tools:
        _print_missing_python_tools(missing_python_tools)
    if missing_node_tools:
        print("QUALITY_ENV_MISSING_NODE_TOOL", file=sys.stderr)
        print("Missing:", file=sys.stderr)
        print("\n".join(missing_node_tools), file=sys.stderr)
    return 1


def main() -> int:
    environment_ok = preflight()
    if environment_ok != 0:
        return environment_ok

    checks = [
        ([sys.executable, "-m", "ruff", "format", "--check", "."], ROOT / "backend"),
        ([sys.executable, "-m", "ruff", "check", "."], ROOT / "backend"),
        ([sys.executable, "-m", "mypy", "src", "tests"], ROOT / "backend"),
        ([sys.executable, str(ROOT / "scripts" / "check_alembic_heads.py")], ROOT),
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(TMP / "meta-pytest-basetemp"),
                "tests/meta",
            ],
            ROOT,
        ),
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(TMP / "backend-pytest-basetemp"),
            ],
            ROOT / "backend",
        ),
        ([NPM, "run", "type-check"], ROOT / "frontend"),
        ([NPM, "run", "test", "--", "--run"], ROOT / "frontend"),
    ]

    for command, cwd in checks:
        result = run(command, cwd=cwd)
        if result != 0:
            return result
    return 0


def _probe(command: list[str], *, cwd: Path) -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TMP)
    env["TEMP"] = str(TMP)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode


def _print_missing_python_tools(missing: list[str]) -> None:
    print("QUALITY_ENV_MISSING_PYTHON_TOOL", file=sys.stderr)
    print(file=sys.stderr)
    print("Current interpreter:", file=sys.stderr)
    print(sys.executable, file=sys.stderr)
    print(file=sys.stderr)
    print("Missing:", file=sys.stderr)
    print("\n".join(missing), file=sys.stderr)
    print(file=sys.stderr)
    print("Expected project interpreter:", file=sys.stderr)
    print(EXPECTED_PROJECT_INTERPRETER, file=sys.stderr)
    print(file=sys.stderr)
    print("Run:", file=sys.stderr)
    print(r".\backend\.venv\Scripts\python.exe scripts\check_all.py", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
