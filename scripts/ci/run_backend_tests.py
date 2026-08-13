"""Run the backend unit test suite for CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=BACKEND,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
