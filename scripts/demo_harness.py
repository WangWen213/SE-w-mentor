from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def run() -> int:
    from se_mentor.demo.harness_demo import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
