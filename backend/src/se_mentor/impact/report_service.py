from __future__ import annotations

import json
import logging
from dataclasses import asdict
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.evidence.bundle import EvidenceBundle
from se_mentor.impact.direct import DirectImpact
from se_mentor.impact.indirect import IndirectImpact
from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.llm.prompts.impact import IMPACT_REPORT_PROMPT_SUMMARY
from se_mentor.models.governance import ImpactReport, ImpactReportStatus

LOGGER = logging.getLogger("se_mentor.impact.report_service")


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
        total_started = perf_counter()
        allowed_refs = {item.evidence_id for item in evidence_bundle.items}
        llm_payload = self._llm_payload(evidence_bundle, direct_impacts, indirect_impacts, unknowns)
        input_text = json.dumps(llm_payload, sort_keys=True)
        provider_started = perf_counter()
        response = self.provider.complete(
            LLMRequest(
                prompt_summary=IMPACT_REPORT_PROMPT_SUMMARY,
                input_text=input_text,
            )
        )
        provider_ms = int((perf_counter() - provider_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.provider task_id=%s proposal_id=%s duration_ms=%s "
                "prompt_chars=%s input_tokens=%s output_tokens=%s"
            ),
            task_id,
            proposal_id,
            provider_ms,
            len(input_text),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        parse_started = perf_counter()
        narrative = _parse_response(response.content)
        fact_refs = tuple(str(ref) for ref in narrative.get("fact_refs", ()))
        hallucinated = tuple(ref for ref in fact_refs if ref not in allowed_refs)
        if hallucinated:
            raise ImpactReportGenerationError(
                f"hallucinated evidence refs: {', '.join(hallucinated)}"
            )
        parse_ms = int((perf_counter() - parse_started) * 1000)

        persist_started = perf_counter()
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
        persist_ms = int((perf_counter() - persist_started) * 1000)
        LOGGER.info(
            (
                "[perf] impact.persist task_id=%s proposal_id=%s duration_ms=%s "
                "evidence_count=%s fact_ref_count=%s"
            ),
            task_id,
            proposal_id,
            persist_ms,
            len(evidence_bundle.items),
            len(fact_refs),
        )
        LOGGER.info(
            (
                "[perf] impact.total task_id=%s proposal_id=%s duration_ms=%s "
                "provider_ms=%s parse_ms=%s persist_ms=%s"
            ),
            task_id,
            proposal_id,
            int((perf_counter() - total_started) * 1000),
            provider_ms,
            parse_ms,
            persist_ms,
        )
        LOGGER.info(
            (
                "[perf] impact-report task_id=%s proposal_id=%s total_ms=%s "
                "provider_ms=%s parse_ms=%s persist_ms=%s evidence_count=%s "
                "direct_count=%s indirect_count=%s unknown_count=%s fact_ref_count=%s"
            ),
            task_id,
            proposal_id,
            int((perf_counter() - total_started) * 1000),
            provider_ms,
            parse_ms,
            persist_ms,
            len(evidence_bundle.items),
            len(direct_impacts),
            len(indirect_impacts),
            len(unknowns),
            len(fact_refs),
        )
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
            "language": "zh-CN",
            "language_instruction": (
                "User-facing natural-language values MUST be Simplified Chinese. "
                "Keep JSON property names unchanged."
            ),
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
        candidate = _extract_json_object(content)
        if candidate is None:
            raise ImpactReportGenerationError("invalid impact report JSON") from exc
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as nested:
            raise ImpactReportGenerationError("invalid impact report JSON") from nested
    if not isinstance(data, dict):
        raise ImpactReportGenerationError("invalid impact report JSON")
    return data


def _extract_json_object(content: str) -> str | None:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        return content[index : index + end]
    return None


def _serialize_impact(impact: DirectImpact | IndirectImpact) -> dict[str, Any]:
    data = asdict(impact)
    return {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}
