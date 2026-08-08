from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.code_index import (
    CodeSymbol,
    CodeSymbolKind,
    CodeSymbolRelation,
    CodeSymbolRelationType,
)


@dataclass(frozen=True)
class RelationExtractionResult:
    relation_count: int
    unresolved_edges: tuple[str, ...]


class RelationExtractor:
    def __init__(self, session: Session) -> None:
        self.session = session

    def extract(
        self, project_id: str, project_root: str | Path, revision: str
    ) -> RelationExtractionResult:
        root = Path(project_root).resolve()
        symbols = self.session.scalars(
            select(CodeSymbol).where(
                CodeSymbol.project_id == project_id, CodeSymbol.revision == revision
            )
        ).all()
        by_name = {symbol.qualified_name: symbol for symbol in symbols}
        by_module = {
            symbol.qualified_name: symbol
            for symbol in symbols
            if symbol.kind in {CodeSymbolKind.MODULE, CodeSymbolKind.FUNCTION, CodeSymbolKind.API}
        }
        relation_count = 0
        unresolved: list[str] = []
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            module = rel[:-3].replace("/", ".")
            source = by_name.get(module)
            if source is None:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except SyntaxError:
                unresolved.append(f"{rel}:syntax-error")
                continue
            visitor = _RelationVisitor(module)
            visitor.visit(tree)
            for imported in visitor.imports:
                target = by_module.get(imported.split(".", 1)[0]) or by_module.get(imported)
                if target is not None and target.id != source.id:
                    relation_count += self._add(source, target, CodeSymbolRelationType.IMPORTS, rel)
                else:
                    unresolved.append(f"{rel}:IMPORTS:{imported}")
            for call in visitor.calls:
                target = _resolve_call(call, module, by_name)
                if target is not None and target.id != source.id:
                    relation_count += self._add(source, target, CodeSymbolRelationType.CALLS, rel)
                else:
                    unresolved.append(f"{rel}:CALLS:{call}")
            for table in visitor.read_tables:
                relation_count += self._add(
                    source,
                    source,
                    CodeSymbolRelationType.READS_TABLE,
                    rel,
                    allow_self=True,
                    detail=table,
                )
            for table in visitor.write_tables:
                relation_count += self._add(
                    source,
                    source,
                    CodeSymbolRelationType.WRITES_TABLE,
                    rel,
                    allow_self=True,
                    detail=table,
                )
            if visitor.serializes:
                relation_count += self._add(
                    source, source, CodeSymbolRelationType.SERIALIZES, rel, allow_self=True
                )
            if rel.startswith("test_"):
                for call in visitor.calls:
                    target = _resolve_call(call, module, by_name)
                    if target is not None and target.id != source.id:
                        relation_count += self._add(
                            source, target, CodeSymbolRelationType.TESTS, rel
                        )
        self.session.flush()
        return RelationExtractionResult(relation_count, tuple(unresolved))

    def related_symbols(self, source_symbol_id: str, *, depth: int = 1) -> tuple[str, ...]:
        seen = {source_symbol_id}
        frontier = {source_symbol_id}
        for _ in range(depth):
            rows = self.session.scalars(
                select(CodeSymbolRelation).where(CodeSymbolRelation.source_symbol_id.in_(frontier))
            ).all()
            frontier = {row.target_symbol_id for row in rows if row.target_symbol_id not in seen}
            seen.update(frontier)
        return tuple(sorted(seen - {source_symbol_id}))

    def _add(
        self,
        source: CodeSymbol,
        target: CodeSymbol,
        relation_type: CodeSymbolRelationType,
        relative_path: str,
        *,
        allow_self: bool = False,
        detail: str | None = None,
    ) -> int:
        if source.id == target.id and not allow_self:
            return 0
        if source.id == target.id:
            candidates = self.session.scalars(
                select(CodeSymbol).where(
                    CodeSymbol.project_id == source.project_id,
                    CodeSymbol.revision == source.revision,
                    CodeSymbol.id != source.id,
                )
            ).all()
            if not candidates:
                return 0
            target = candidates[0]
        existing = self.session.scalar(
            select(CodeSymbolRelation).where(
                CodeSymbolRelation.source_symbol_id == source.id,
                CodeSymbolRelation.target_symbol_id == target.id,
                CodeSymbolRelation.relation_type == relation_type,
            )
        )
        if existing is not None:
            return 0
        self.session.add(
            CodeSymbolRelation(
                source_symbol_id=source.id,
                source_project_id=source.project_id,
                source_revision=source.revision,
                target_symbol_id=target.id,
                target_project_id=target.project_id,
                target_revision=target.revision,
                relation_type=relation_type,
                evidence_json=json.dumps(
                    {"relative_path": relative_path, "certainty": "confirmed", "detail": detail}
                ),
            )
        )
        return 1


class _RelationVisitor(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.serializes = False
        self.read_tables: list[str] = []
        self.write_tables: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            self.imports.append(node.module)

    def visit_Call(self, node: ast.Call) -> None:
        name = ast.unparse(node.func)
        self.calls.append(name.split(".")[-1])
        if name.endswith("dumps") or name.endswith("loads"):
            self.serializes = True
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                sql = arg.value.upper()
                if "SELECT" in sql:
                    self.read_tables.append(_table(sql))
                if "INSERT" in sql or "UPDATE" in sql or "DELETE" in sql:
                    self.write_tables.append(_table(sql))
        self.generic_visit(node)


def _resolve_call(call: str, module: str, by_name: dict[str, CodeSymbol]) -> CodeSymbol | None:
    return by_name.get(f"{module}.{call}") or next(
        (symbol for name, symbol in by_name.items() if name.endswith(f".{call}")),
        None,
    )


def _table(sql: str) -> str:
    parts = sql.replace("(", " ").split()
    for marker in ("FROM", "INTO", "UPDATE"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1].lower()
    return "unknown"
