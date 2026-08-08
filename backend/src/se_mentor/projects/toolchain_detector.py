from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ToolchainKind(StrEnum):
    PYTHON = "PYTHON"
    TYPESCRIPT = "TYPESCRIPT"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ToolchainDetection:
    kind: ToolchainKind
    confidence: float
    manifests: tuple[str, ...] = ()
    test_frameworks: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    executed_commands: tuple[str, ...] = ()
    limit_exceeded: bool = False
    status: str = "OK"
    evidence: tuple[str, ...] = field(default_factory=tuple)


def detect_toolchain(project_root: str | Path, *, max_files: int = 5000) -> ToolchainDetection:
    root = Path(project_root).resolve()
    manifests: set[str] = set()
    frameworks: set[str] = set()
    evidence: list[str] = []
    scanned = 0

    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        scanned += 1
        if scanned > max_files:
            return ToolchainDetection(
                kind=ToolchainKind.UNKNOWN,
                confidence=0.0,
                limit_exceeded=True,
                status="LIMIT_EXCEEDED",
                unknowns=("repository file scan limit exceeded",),
            )
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        name = path.name
        if name in {"pyproject.toml", "requirements.txt", "setup.py", "pytest.ini"}:
            manifests.add(name)
            evidence.append(rel)
        if name == "package.json":
            manifests.add(name)
            evidence.append(rel)
            _detect_package_json(path, frameworks)
        if name.startswith("test_") and path.suffix == ".py":
            frameworks.add("pytest")
        if name == "pyproject.toml":
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "pytest" in content:
                frameworks.add("pytest")
        if name == "requirements.txt":
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "pytest" in content:
                frameworks.add("pytest")

    has_python = bool(manifests.intersection({"pyproject.toml", "requirements.txt", "setup.py"}))
    has_ts = "package.json" in manifests
    if has_python and has_ts:
        kind = ToolchainKind.MIXED
    elif has_python:
        kind = ToolchainKind.PYTHON
    elif has_ts:
        kind = ToolchainKind.TYPESCRIPT
    else:
        return ToolchainDetection(
            kind=ToolchainKind.UNKNOWN,
            confidence=0.0,
            unknowns=("no supported manifest found",),
        )
    confidence = 0.9 if frameworks else 0.7
    return ToolchainDetection(
        kind=kind,
        confidence=confidence,
        manifests=tuple(sorted(manifests)),
        test_frameworks=tuple(sorted(frameworks)),
        evidence=tuple(sorted(evidence)),
    )


def _detect_package_json(path: Path, frameworks: set[str]) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    scripts = data.get("scripts", {})
    text = json.dumps(scripts)
    if "vitest" in text:
        frameworks.add("vitest")
    if "jest" in text:
        frameworks.add("jest")
