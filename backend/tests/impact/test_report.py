from __future__ import annotations

import json
from pathlib import Path

import pytest
from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.evidence.bundle import EvidenceBundleBuilder, EvidenceItem
from se_mentor.impact.direct import DirectImpact, DirectImpactKind
from se_mentor.impact.indirect import IndirectImpact
from se_mentor.impact.report_service import ImpactReportGenerationError, ImpactReportService
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.governance import ImpactReport, ImpactReportStatus


def test_T043_report_rejects_hallucinated_evidence_and_preserves_unknowns(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "impact-report.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    bundle = EvidenceBundleBuilder(
        [
            EvidenceItem(
                evidence_id="code:api",
                kind="code",
                revision=REVISION,
                uri="source://backend/src/app/api.py",
                summary="API direct impact",
                freshness="fresh",
                confidence="confirmed",
                verified=True,
            )
        ]
    ).build(task_id=ids["task_id"], revision=REVISION, required_refs=("code:api",))
    direct = DirectImpact(
        DirectImpactKind.API,
        "backend/src/app/api.py",
        "app.api.get_user",
        "confirmed",
        ("code:api",),
    )
    indirect = IndirectImpact(
        "backend/src/app/config.py",
        "app.config.Settings",
        2,
        "IMPORTS",
        "uncertain",
        ("knowledge:stale",),
        "stale_knowledge",
    )

    with session_scope(session_factory) as session:
        old = ImpactReport(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            base_revision=REVISION,
            direct_impacts_json='["old"]',
            uncertainties_json='["old"]',
            evidence_json='[{"evidence_id":"old"}]',
            status=ImpactReportStatus.CURRENT,
        )
        session.add(old)
        session.flush()
        bad = ImpactReportService(
            session,
            MockLLMProvider(
                model="mock",
                script=(
                    MockResponse(
                        match="impact report",
                        content='{"narrative":"bad","fact_refs":["missing:evidence"]}',
                        input_tokens=3,
                        output_tokens=5,
                    ),
                ),
            ),
        )
        with pytest.raises(ImpactReportGenerationError, match="hallucinated"):
            bad.generate(
                task_id=ids["task_id"],
                proposal_id=ids["proposal_id"],
                base_revision=REVISION,
                evidence_bundle=bundle,
                direct_impacts=(direct,),
                indirect_impacts=(indirect,),
                unknowns=("backend/src/app/config.py:stale_knowledge",),
            )
        good = ImpactReportService(
            session,
            MockLLMProvider(
                model="mock",
                script=(
                    MockResponse(
                        match="impact report",
                        content=(
                            '{"narrative":"ok","fact_refs":["code:api"],"risks":["stale config"]}'
                        ),
                        input_tokens=4,
                        output_tokens=6,
                    ),
                ),
            ),
        )
        report = good.generate(
            task_id=ids["task_id"],
            proposal_id=ids["proposal_id"],
            base_revision=REVISION,
            evidence_bundle=bundle,
            direct_impacts=(direct,),
            indirect_impacts=(indirect,),
            unknowns=("backend/src/app/config.py:stale_knowledge",),
        )

    assert old.status == ImpactReportStatus.STALE
    assert report.status == ImpactReportStatus.CURRENT
    assert json.loads(report.evidence_json) == [{"evidence_id": "code:api"}]
    assert report.direct_impacts_json is not None
    assert report.uncertainties_json is not None
    assert "missing:evidence" not in report.direct_impacts_json
    assert "stale_knowledge" in report.uncertainties_json
