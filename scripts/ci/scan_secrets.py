"""Scan tracked files for committed secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
DENYLISTED_SUFFIXES = {
    ".db",
    ".key",
    ".pem",
    ".sqlite",
    ".sqlite3",
}
DENYLISTED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
}
ALLOW_HINTS = (
    "abcdefghijklmnop",
    "abcdefghijklmnopqrstuvwxyz",
    "dummy",
    "example",
    "fake",
    "must-not-be-used",
    "not-used",
    "not_configured",
    "placeholder",
    "redacted",
    "sample",
    "test",
)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES = [
    Rule("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    Rule("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    Rule("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    Rule(
        "bearer-token",
        re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    ),
    Rule(
        "secret-assignment",
        re.compile(
            r"\b(password|passwd|api[_-]?key|access[_-]?key|secret|token)\b"
            r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "alibaba-secret",
        re.compile(
            r"\b(aliyun|alibaba)[A-Za-z0-9_-]*(access[_-]?key|secret)[A-Za-z0-9_-]*"
            r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]",
            re.IGNORECASE,
        ),
    ),
]


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(result.returncode)

    paths = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [root / path for path in paths if path]


def is_binary(path: Path) -> bool:
    chunk = path.read_bytes()[:4096]
    return b"\0" in chunk


def is_allowlisted(text: str) -> bool:
    lowered = text.lower()
    if any(hint in lowered for hint in ALLOW_HINTS):
        return True
    return bool(re.search(r"['\"]?\$[{]?[A-Z0-9_]+[}]?['\"]?", text))


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size > MAX_FILE_BYTES:
        return False
    return not is_binary(path)


def find_secrets(root: Path) -> list[str]:
    findings: list[str] = []
    for path in tracked_files(root):
        rel_path = path.relative_to(root)
        if (
            rel_path.name in DENYLISTED_NAMES
            or rel_path.suffix.lower() in DENYLISTED_SUFFIXES
        ):
            findings.append(f"{rel_path}:0:denylisted-secret-file")
            continue
        if not should_scan(path):
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule in RULES:
                match = rule.pattern.search(line)
                if not match or is_allowlisted(match.group(0)):
                    continue
                findings.append(f"{rel_path}:{line_no}:{rule.name}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    findings = find_secrets(root)
    if findings:
        sys.stderr.write("Secret scan failed. Findings:\n")
        for finding in findings:
            sys.stderr.write(f"- {finding}\n")
        return 1

    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
