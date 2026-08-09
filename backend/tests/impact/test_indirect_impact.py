from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.impact.direct import DirectImpact, DirectImpactKind
from se_mentor.impact.indirect import IndirectImpactAnalyzer
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.models.code_index import (
    CodeIndex,
    CodeIndexStatus,
    CodeSymbol,
    CodeSymbolKind,
    CodeSymbolRelation,
    CodeSymbolRelationType,
)
from se_mentor.models.knowledge import KnowledgeStatus, KnowledgeType


def test_T041_dependency_cycle_terminates_and_marks_uncertain_edges(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "indirect-impact.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        index = CodeIndex(
            project_id=ids["project_id"],
            revision=REVISION,
            language="python",
            status=CodeIndexStatus.READY,
            index_generation=1,
            evidence_json="[]",
        )
        session.add(index)
        session.flush()
        api = _symbol(index, ids["project_id"], "backend/src/app/api.py", "app.api.get_user")
        service = _symbol(
            index,
            ids["project_id"],
            "backend/src/app/service.py",
            "app.service.load_user",
        )
        config = _symbol(
            index,
            ids["project_id"],
            "backend/src/app/config.py",
            "app.config.Settings",
            CodeSymbolKind.CLASS,
        )
        session.add_all([api, service, config])
        session.flush()
        session.add_all(
            [
                _relation(api, service, CodeSymbolRelationType.CALLS),
                _relation(service, api, CodeSymbolRelationType.CALLS),
                _relation(service, config, CodeSymbolRelationType.IMPORTS),
            ]
        )
        KnowledgeRepository(session).add(
            project_id=ids["project_id"],
            key="settings-drift",
            knowledge_type=KnowledgeType.CONSTRAINT,
            status=KnowledgeStatus.STALE,
            scope_paths=("backend/src/app/config.py",),
            summary="Settings layout may be stale.",
        )
        session.flush()
        result = IndirectImpactAnalyzer(session).expand(
            project_id=ids["project_id"],
            revision=REVISION,
            direct_impacts=(
                DirectImpact(
                    DirectImpactKind.API,
                    api.relative_path,
                    api.qualified_name,
                    "confirmed",
                    (f"code-index://{REVISION}/{api.id}",),
                ),
            ),
            max_depth=4,
            max_nodes=8,
        )

    assert result.truncated is False
    assert [impact.symbol_name for impact in result.impacts] == [
        "app.service.load_user",
        "app.config.Settings",
    ]
    assert result.impacts[0].confidence == "confirmed"
    assert result.impacts[1].confidence == "uncertain"
    assert result.impacts[1].uncertainty_reason == "stale_knowledge"
    assert result.unknowns == ("backend/src/app/config.py:stale_knowledge",)


def _symbol(
    index: CodeIndex,
    project_id: str,
    relative_path: str,
    qualified_name: str,
    kind: CodeSymbolKind = CodeSymbolKind.FUNCTION,
) -> CodeSymbol:
    return CodeSymbol(
        code_index_id=index.id,
        project_id=project_id,
        revision=REVISION,
        symbol_key=f"{qualified_name}:symbol",
        qualified_name=qualified_name,
        kind=kind,
        relative_path=relative_path,
        signature_hash="1" * 64,
    )


def _relation(
    source: CodeSymbol,
    target: CodeSymbol,
    relation_type: CodeSymbolRelationType,
) -> CodeSymbolRelation:
    return CodeSymbolRelation(
        source_symbol_id=source.id,
        source_project_id=source.project_id,
        source_revision=source.revision,
        target_symbol_id=target.id,
        target_project_id=target.project_id,
        target_revision=target.revision,
        relation_type=relation_type,
        evidence_json='{"source":"test"}',
    )
