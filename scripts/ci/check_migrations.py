"""Run migration policy checks for CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_alembic_heads.py")],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
