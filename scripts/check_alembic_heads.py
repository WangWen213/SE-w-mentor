from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    heads = [line for line in result.stdout.splitlines() if line.strip()]
    if len(heads) > 1:
        sys.stderr.write("Alembic must have exactly one head.\n")
        sys.stderr.write(result.stdout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
