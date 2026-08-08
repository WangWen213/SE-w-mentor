from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from se_mentor.security.path_policy import PathPolicy


class SignatureStatus(StrEnum):
    OK = "OK"
    DEGRADED_PARSE_ERROR = "DEGRADED_PARSE_ERROR"
    MISSING_SYMBOL = "MISSING_SYMBOL"
    OUTSIDE_PROJECT = "OUTSIDE_PROJECT"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class CodeKnowledgeSignature:
    status: SignatureStatus
    revision: str
    relative_path: str
    file_hash: str
    ast_hash: str | None
    symbol_hash: str | None
    signature_hash: str


class KnowledgeSignatureBuilder:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.policy = PathPolicy(self.project_root)

    def for_file(
        self,
        relative_path: str,
        *,
        revision: str,
        symbol_name: str | None = None,
    ) -> CodeKnowledgeSignature:
        raw_path = Path(relative_path)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            return _empty(SignatureStatus.OUTSIDE_PROJECT, revision, relative_path)
        decision = self.policy.resolve(relative_path)
        if not decision.allowed:
            status = (
                SignatureStatus.OUTSIDE_PROJECT
                if decision.reason == "REALPATH_OUTSIDE_PROJECT"
                else SignatureStatus.NOT_FOUND
            )
            return _empty(status, revision, relative_path)
        assert decision.path is not None and decision.relative_path is not None
        content = decision.path.read_text(encoding="utf-8", errors="replace")
        file_hash = _sha(content)
        try:
            tree = ast.parse(content, filename=decision.relative_path)
        except SyntaxError:
            return CodeKnowledgeSignature(
                status=SignatureStatus.DEGRADED_PARSE_ERROR,
                revision=revision,
                relative_path=decision.relative_path,
                file_hash=file_hash,
                ast_hash=None,
                symbol_hash=None,
                signature_hash=_sha(f"{revision}:{decision.relative_path}:{file_hash}:degraded"),
            )
        if symbol_name is not None:
            symbol = _find_symbol(tree, symbol_name)
            if symbol is None:
                return CodeKnowledgeSignature(
                    status=SignatureStatus.MISSING_SYMBOL,
                    revision=revision,
                    relative_path=decision.relative_path,
                    file_hash=file_hash,
                    ast_hash=_ast_hash(tree),
                    symbol_hash=None,
                    signature_hash=_sha(f"{revision}:{decision.relative_path}:{file_hash}:missing"),
                )
            symbol_hash = _ast_hash(symbol)
        else:
            symbol_hash = None
        ast_hash = _ast_hash(tree)
        return CodeKnowledgeSignature(
            status=SignatureStatus.OK,
            revision=revision,
            relative_path=decision.relative_path,
            file_hash=file_hash,
            ast_hash=ast_hash,
            symbol_hash=symbol_hash,
            signature_hash=_sha(f"{revision}:{decision.relative_path}:{file_hash}:{ast_hash}:{symbol_hash}"),
        )


def _empty(status: SignatureStatus, revision: str, relative_path: str) -> CodeKnowledgeSignature:
    signature_hash = _sha(f"{revision}:{relative_path}:{status}")
    return CodeKnowledgeSignature(status, revision, relative_path, "", None, None, signature_hash)


def _find_symbol(tree: ast.AST, symbol_name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name == symbol_name:
                return node
    return None


def _ast_hash(node: ast.AST) -> str:
    normalized = ast.dump(node, annotate_fields=True, include_attributes=False)
    return _sha(normalized)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
