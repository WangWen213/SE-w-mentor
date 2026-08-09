from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.code_index import CodeSymbol, CodeSymbolKind
from se_mentor.models.project import Project


class DirectImpactKind(StrEnum):
    API = "API"
    DTO = "DTO"
    TABLE = "TABLE"
    TEST = "TEST"
    FILE = "FILE"


@dataclass(frozen=True)
class DirectImpact:
    kind: DirectImpactKind
    relative_path: str
    symbol_name: str
    confidence: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class DirectImpactResult:
    impacts: tuple[DirectImpact, ...]
    unknowns: tuple[str, ...]


class DirectImpactAnalyzer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def analyze(
        self,
        *,
        project_id: str,
        revision: str,
        proposal_scope: tuple[str, ...],
        diff_text: str,
    ) -> DirectImpactResult:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError("project not found")
        root = Path(project.root_path)
        changed_paths = _changed_paths(diff_text).union(_normalize_paths(proposal_scope))
        symbols = self.session.scalars(
            select(CodeSymbol).where(
                CodeSymbol.project_id == project_id,
                CodeSymbol.revision == revision,
                CodeSymbol.relative_path.in_(changed_paths),
            )
        ).all()
        impacts: list[DirectImpact] = []
        impacted_names: set[str] = set()
        for symbol in symbols:
            simple_name = symbol.qualified_name.rsplit(".", 1)[-1]
            if symbol.kind == CodeSymbolKind.API:
                impacts.append(_symbol_impact(DirectImpactKind.API, symbol))
                impacted_names.add(simple_name)
            elif symbol.kind == CodeSymbolKind.CLASS and simple_name.endswith("DTO"):
                impacts.append(_symbol_impact(DirectImpactKind.DTO, symbol))
                impacted_names.add(simple_name)

        for rel in changed_paths:
            path = root / rel
            if path.suffix != ".py":
                impacts.append(
                    DirectImpact(
                        DirectImpactKind.FILE,
                        rel,
                        rel,
                        "unknown",
                        (f"diff://{revision}/{rel}",),
                    )
                )
                continue
            if path.exists():
                impacts.extend(_table_impacts(path, rel, revision))

        impacts.extend(_test_impacts(root, impacted_names, revision))
        confirmed = tuple(
            sorted(_dedupe(impacts), key=lambda item: (item.kind.value, item.relative_path, item.symbol_name))
        )
        unknowns = tuple(impact.relative_path for impact in confirmed if impact.confidence == "unknown")
        return DirectImpactResult(confirmed, unknowns)


def _symbol_impact(kind: DirectImpactKind, symbol: CodeSymbol) -> DirectImpact:
    return DirectImpact(
        kind,
        symbol.relative_path,
        symbol.qualified_name,
        "confirmed",
        (f"code-index://{symbol.revision}/{symbol.id}",),
    )


def _table_impacts(path: Path, relative_path: str, revision: str) -> tuple[DirectImpact, ...]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    tables = sorted(set(_extract_tables(text)))
    return tuple(
        DirectImpact(
            DirectImpactKind.TABLE,
            relative_path,
            table,
            "confirmed",
            (f"source://{revision}/{relative_path}#sql:{table}",),
        )
        for table in tables
    )


def _test_impacts(root: Path, names: set[str], revision: str) -> tuple[DirectImpact, ...]:
    if not names:
        return ()
    impacts: list[DirectImpact] = []
    for path in sorted(root.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(name in text for name in names):
            rel = path.relative_to(root).as_posix()
            impacts.append(
                DirectImpact(
                    DirectImpactKind.TEST,
                    rel,
                    path.stem,
                    "confirmed",
                    (f"source://{revision}/{rel}",),
                )
            )
    return tuple(impacts)


def _changed_paths(diff_text: str) -> set[str]:
    paths: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            paths.add(line.removeprefix("+++ b/"))
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                paths.add(parts[3].removeprefix("b/"))
    return paths


def _normalize_paths(paths: tuple[str, ...]) -> set[str]:
    return {path.replace("\\", "/").lstrip("/") for path in paths}


def _extract_tables(text: str) -> tuple[str, ...]:
    pattern = re.compile(r"\b(?:FROM|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
    return tuple(match.group(1).lower() for match in pattern.finditer(text))


def _dedupe(impacts: list[DirectImpact]) -> tuple[DirectImpact, ...]:
    seen: set[tuple[DirectImpactKind, str, str]] = set()
    unique: list[DirectImpact] = []
    for impact in impacts:
        key = (impact.kind, impact.relative_path, impact.symbol_name)
        if key not in seen:
            seen.add(key)
            unique.append(impact)
    return tuple(unique)
