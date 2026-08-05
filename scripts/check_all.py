from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"
TMP = ROOT / ".tmp" / "check-all"


def run(command: list[str], *, cwd: Path) -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TMP)
    env["TEMP"] = str(TMP)
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


def main() -> int:
    checks = [
        ([sys.executable, "-m", "ruff", "format", "--check", "."], ROOT / "backend"),
        ([sys.executable, "-m", "ruff", "check", "."], ROOT / "backend"),
        ([sys.executable, "-m", "mypy", "src", "tests"], ROOT / "backend"),
        ([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"], ROOT / "backend"),
        ([NPM, "run", "type-check"], ROOT / "frontend"),
        ([NPM, "run", "test", "--", "--run"], ROOT / "frontend"),
    ]

    for command, cwd in checks:
        result = run(command, cwd=cwd)
        if result != 0:
            return result
    return 0


if __name__ == "__main__":
    sys.exit(main())
