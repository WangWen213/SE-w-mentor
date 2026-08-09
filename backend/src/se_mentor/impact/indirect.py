from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from se_mentor.impact.direct import DirectImpact
from se_mentor.models.code_index import CodeSymbol, CodeSymbolRelation
from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeStatus


@dataclass(frozen=True)
class IndirectImpact:
    relative_path: str
    symbol_name: str
    depth: int
    via_relation: str
    confidence: str
    evidence_refs: tuple[str, ...]
    uncertainty_reason: str | None = None


@dataclass(frozen=True)
class IndirectImpactResult:
    impacts: tuple[IndirectImpact, ...]
    unknowns: tuple[str, ...]
    truncated: bool


class IndirectImpactAnalyzer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def expand(
        self,
        *,
        project_id: str,
        revision: str,
        direct_impacts: tuple[DirectImpact, ...],
        max_depth: int = 3,
        max_nodes: int = 50,
    ) -> IndirectImpactResult:
        start_ids = tuple(_symbol_id(ref) for impact in direct_impacts for ref in impact.evidence_refs)
        frontier = {symbol_id for symbol_id in start_ids if symbol_id is not None}
        seen = set(frontier)
        impacts: list[IndirectImpact] = []
        unknowns: list[str] = []
        truncated = False

        for depth in range(1, max_depth + 1):
            if not frontier:
                break
            rows = self.session.scalars(
                select(CodeSymbolRelation)
                .where(
                    or_(
                        CodeSymbolRelation.source_symbol_id.in_(frontier),
                        CodeSymbolRelation.target_symbol_id.in_(frontier),
                    )
                )
                .order_by(CodeSymbolRelation.relation_type, CodeSymbolRelation.target_symbol_id)
            ).all()
            next_frontier: set[str] = set()
            for relation in rows:
                neighbor_id = (
                    relation.target_symbol_id
                    if relation.source_symbol_id in frontier
                    else relation.source_symbol_id
                )
                if neighbor_id in seen:
                    continue
                if len(seen) >= max_nodes:
                    truncated = True
                    break
                symbol = self.session.get(CodeSymbol, neighbor_id)
                if symbol is None or symbol.project_id != project_id or symbol.revision != revision:
                    continue
                confidence, reason, evidence = self._confidence(symbol)
                if reason is not None:
                    unknowns.append(f"{symbol.relative_path}:{reason}")
                impacts.append(
                    IndirectImpact(
                        symbol.relative_path,
                        symbol.qualified_name,
                        depth,
                        relation.relation_type,
                        confidence,
                        (f"relation://{relation.id}", *evidence),
                        reason,
                    )
                )
                seen.add(neighbor_id)
                next_frontier.add(neighbor_id)
            if truncated:
                break
            frontier = next_frontier

        return IndirectImpactResult(tuple(impacts), tuple(dict.fromkeys(unknowns)), truncated)

    def _confidence(self, symbol: CodeSymbol) -> tuple[str, str | None, tuple[str, ...]]:
        knowledge = self.session.scalars(
            select(EngineeringKnowledge).where(
                EngineeringKnowledge.project_id == symbol.project_id,
                EngineeringKnowledge.status.in_(
                    [KnowledgeStatus.STALE, KnowledgeStatus.CONFLICTING]
                ),
            )
        ).all()
        for item in knowledge:
            if symbol.relative_path in _scope_paths(item.scope_json):
                return "uncertain", "stale_knowledge", (f"knowledge://{item.id}",)
        return "confirmed", None, ()


def _symbol_id(ref: str) -> str | None:
    if not ref.startswith("code-index://"):
        return None
    return ref.rsplit("/", 1)[-1]


def _scope_paths(value: str) -> tuple[str, ...]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if isinstance(data, list):
        return tuple(str(item) for item in data)
    return ()
