from __future__ import annotations

import ast
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.code_index import CodeIndex, CodeIndexStatus, CodeSymbol, CodeSymbolKind

_EXCLUDED_DIRS = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".sementor",
    ".tmp",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "evidence",
    "node_modules",
}


@dataclass(frozen=True)
class IndexBuildResult:
    index_id: str
    symbol_count: int
    parse_errors: tuple[str, ...]


class PythonIndexer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build(self, project_id: str, project_root: str | Path, revision: str) -> IndexBuildResult:
        root = Path(project_root).resolve()
        existing = self.session.scalar(
            select(CodeIndex).where(
                CodeIndex.project_id == project_id,
                CodeIndex.revision == revision,
                CodeIndex.language == "python",
            )
        )
        if existing is not None:
            count = len(existing.symbols)
            errors = _parse_errors(existing.evidence_json)
            return IndexBuildResult(existing.id, count, errors)
        index = CodeIndex(
            project_id=project_id,
            revision=revision,
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json="[]",
        )
        self.session.add(index)
        self.session.flush()
        parse_errors: list[str] = []
        symbol_count = 0
        seen_symbol_keys: set[str] = set()
        for path in _iter_python_files(root):
            rel = path.relative_to(root).as_posix()
            module = rel[:-3].replace("/", ".")
            symbol_count += self._add_symbol(
                index,
                project_id,
                revision,
                f"{module}:module",
                module,
                CodeSymbolKind.MODULE,
                rel,
                path.read_text(encoding="utf-8", errors="ignore"),
                seen_symbol_keys,
            )
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except SyntaxError as exc:
                parse_errors.append(f"{rel}: SyntaxError: {exc.msg}")
                continue
            visitor = _SymbolVisitor(module)
            visitor.visit(tree)
            for symbol in visitor.symbols:
                symbol_count += self._add_symbol(
                    index,
                    project_id,
                    revision,
                    symbol.symbol_key,
                    symbol.qualified_name,
                    symbol.kind,
                    rel,
                    symbol.signature,
                    seen_symbol_keys,
                )
        index.evidence_json = json.dumps({"parse_errors": parse_errors}, sort_keys=True)
        self.session.flush()
        return IndexBuildResult(index.id, symbol_count, tuple(parse_errors))

    def _add_symbol(
        self,
        index: CodeIndex,
        project_id: str,
        revision: str,
        symbol_key: str,
        qualified_name: str,
        kind: CodeSymbolKind,
        relative_path: str,
        signature: str,
        seen_symbol_keys: set[str],
    ) -> int:
        if symbol_key in seen_symbol_keys:
            return 0
        seen_symbol_keys.add(symbol_key)
        self.session.add(
            CodeSymbol(
                code_index_id=index.id,
                project_id=project_id,
                revision=revision,
                symbol_key=symbol_key,
                qualified_name=qualified_name,
                kind=kind,
                relative_path=relative_path,
                signature_hash=hashlib.sha256(signature.encode("utf-8")).hexdigest(),
            )
        )
        return 1


@dataclass(frozen=True)
class _PendingSymbol:
    symbol_key: str
    qualified_name: str
    kind: CodeSymbolKind
    signature: str


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.class_stack: list[str] = []
        self.symbols: list[_PendingSymbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = f"{self.module}.{node.name}"
        self.symbols.append(
            _PendingSymbol(f"{self.module}:{node.name}", qualified, CodeSymbolKind.CLASS, node.name)
        )
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.class_stack:
            owner = ".".join([self.module, *self.class_stack])
            kind = CodeSymbolKind.METHOD
        else:
            owner = self.module
            kind = CodeSymbolKind.TEST if node.name.startswith("test_") else CodeSymbolKind.FUNCTION
            if _has_api_decorator(node):
                kind = CodeSymbolKind.API
        qualified = f"{owner}.{node.name}"
        self.symbols.append(
            _PendingSymbol(f"{owner}:{node.name}", qualified, kind, ast.unparse(node))
        )
        self.generic_visit(node)


def _has_api_decorator(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        text = ast.unparse(decorator)
        if ".get(" in text or ".post(" in text or ".put(" in text or ".delete(" in text:
            return True
    return False


def _parse_errors(evidence_json: str) -> tuple[str, ...]:
    try:
        data = json.loads(evidence_json)
    except json.JSONDecodeError:
        return ()
    if isinstance(data, dict) and isinstance(data.get("parse_errors"), list):
        return tuple(str(item) for item in data["parse_errors"])
    return ()


def _iter_python_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in _EXCLUDED_DIRS]
        current_path = Path(current)
        for name in sorted(files):
            if name.endswith(".py"):
                yield current_path / name
