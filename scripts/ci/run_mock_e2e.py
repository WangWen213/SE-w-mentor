"""Run mock-safe E2E checks for CI without external network dependencies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def run(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode


def main() -> int:
    offline_exit = run(
        [sys.executable, str(ROOT / "scripts" / "run_offline_e2e.py")], ROOT
    )
    if offline_exit != 0:
        return offline_exit

    return run(
        [sys.executable, "-m", "pytest", "tests/e2e/test_offline_determinism.py"],
        BACKEND,
    )


if __name__ == "__main__":
    raise SystemExit(main())
