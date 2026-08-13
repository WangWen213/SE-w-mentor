"""Run security-sensitive backend tests for CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SECURITY_TARGETS = [
    "tests/security",
    "tests/credentials",
    "tests/policy",
    "tests/governance",
]


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *SECURITY_TARGETS],
        cwd=BACKEND,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
