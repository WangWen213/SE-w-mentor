from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    command = [sys.executable, "-m", "alembic"]
    if args.config is not None:
        command.extend(["-c", str(args.config)])
    command.append("heads")

    result = subprocess.run(
        command,
        cwd=args.cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    heads = [
        _extract_revision_id(line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    head_count = len(heads)

    sys.stdout.write(f"Detected head count: {head_count}\n")
    if heads:
        sys.stdout.write("Revision IDs:\n")
        sys.stdout.write("\n".join(heads))
        sys.stdout.write("\n")
    else:
        sys.stdout.write("Revision IDs: <none>\n")

    if head_count == 0:
        sys.stderr.write("No Alembic heads detected; migration state is invalid.\n")
        return 1
    if head_count > 1:
        sys.stderr.write(
            "Multiple Alembic heads detected; migration gate fails closed.\n"
        )
        return 1
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail unless Alembic reports exactly one migration head.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional alembic.ini path for fixture or non-default repositories.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=BACKEND,
        help="Working directory for the Alembic command.",
    )
    return parser.parse_args(argv)


def _extract_revision_id(line: str) -> str:
    return line.strip().split(maxsplit=1)[0]


if __name__ == "__main__":
    sys.exit(main())
