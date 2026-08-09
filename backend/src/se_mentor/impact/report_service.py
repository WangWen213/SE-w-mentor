from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.evidence.bundle import EvidenceBundle
from se_mentor.impact.direct import DirectImpact
from se_mentor.impact.indirect import IndirectImpact
from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.llm.prompts.impact import IMPACT_REPORT_PROMPT_SUMMARY
from se_mentor.models.governance import ImpactReport, ImpactReportStatus


class ImpactReportGenerationError(ValueError):
    pass


class ImpactReportService:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def generate(
        self,
        *,
        task_id: str,
        proposal_id: str,
        base_revision: str,
        evidence_bundle: EvidenceBundle,
        direct_impacts: tuple[DirectImpact, ...],
        indirect_impacts: tuple[IndirectImpact, ...],
        unknowns: tuple[str, ...],
    ) -> ImpactReport:
        allowed_refs = {item.evidence_id for item in evidence_bundle.items}
        llm_payload = self._llm_payload(evidence_bundle, direct_impacts, indirect_impacts, unknowns)
        response = self.provider.complete(
            LLMRequest(
                prompt_summary=IMPACT_REPORT_PROMPT_SUMMARY,
                input_text=json.dumps(llm_payload, sort_keys=True),
            )
        )
        narrative = _parse_response(response.content)
        fact_refs = tuple(str(ref) for ref in narrative.get("fact_refs", ()))
        hallucinated = tuple(ref for ref in fact_refs if ref not in allowed_refs)
        if hallucinated:
            raise ImpactReportGenerationError(
                f"hallucinated evidence refs: {', '.join(hallucinated)}"
            )

        self._stale_current_reports(task_id, proposal_id)
        report = ImpactReport(
            task_id=task_id,
            proposal_id=proposal_id,
            base_revision=base_revision,
            direct_impacts_json=json.dumps(
                [_serialize_impact(impact) for impact in direct_impacts],
                sort_keys=True,
            ),
            indirect_impacts_json=json.dumps(
                [_serialize_impact(impact) for impact in indirect_impacts],
                sort_keys=True,
            ),
            uncertainties_json=json.dumps(
                {
                    "unknowns": unknowns,
                    "risks": tuple(str(item) for item in narrative.get("risks", ())),
                    "narrative": str(narrative.get("narrative", "")),
                },
                sort_keys=True,
            ),
            evidence_json=json.dumps(
                [{"evidence_id": evidence_id} for evidence_id in sorted(fact_refs)],
                sort_keys=True,
            ),
            status=ImpactReportStatus.CURRENT,
        )
        self.session.add(report)
        self.session.flush()
        return report

    def _llm_payload(
        self,
        evidence_bundle: EvidenceBundle,
        direct_impacts: tuple[DirectImpact, ...],
        indirect_impacts: tuple[IndirectImpact, ...],
        unknowns: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "bundle_hash": evidence_bundle.bundle_hash,
            "evidence_ids": [item.evidence_id for item in evidence_bundle.items],
            "direct_impacts": [_serialize_impact(impact) for impact in direct_impacts],
            "indirect_impacts": [_serialize_impact(impact) for impact in indirect_impacts],
            "unknowns": unknowns,
        }

    def _stale_current_reports(self, task_id: str, proposal_id: str) -> None:
        reports = self.session.scalars(
            select(ImpactReport).where(
                ImpactReport.task_id == task_id,
                ImpactReport.proposal_id == proposal_id,
                ImpactReport.status == ImpactReportStatus.CURRENT,
            )
        )
        for report in reports:
            report.status = ImpactReportStatus.STALE


def _parse_response(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ImpactReportGenerationError("invalid impact report JSON") from exc
    if not isinstance(data, dict):
        raise ImpactReportGenerationError("invalid impact report JSON")
    return data


def _serialize_impact(impact: DirectImpact | IndirectImpact) -> dict[str, Any]:
    data = asdict(impact)
    return {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}
