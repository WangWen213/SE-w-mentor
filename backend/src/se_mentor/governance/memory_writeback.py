from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.models.governance import GovernanceDecision, GovernanceDecisionStatus
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeType,
)
from se_mentor.models.task import ChangeProposal, ChangeTask


@dataclass(frozen=True)
class GovernanceMemoryWritebackResult:
    knowledge_id: str
    category: str
    statement: str


class GovernanceMemoryWritebackService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def write_back(self, decision: GovernanceDecision) -> GovernanceMemoryWritebackResult | None:
        candidate = self._candidate(decision)
        if candidate is None:
            return None

        existing = self.session.scalar(
            select(EngineeringKnowledge)
            .where(EngineeringKnowledge.project_id == candidate["project_id"])
            .where(EngineeringKnowledge.knowledge_key == candidate["key"])
            .where(EngineeringKnowledge.version == 1)
        )
        if existing is not None:
            return GovernanceMemoryWritebackResult(
                knowledge_id=existing.id,
                category=str(candidate["category"]),
                statement=existing.summary,
            )

        knowledge = KnowledgeRepository(self.session).add(
            project_id=str(candidate["project_id"]),
            key=str(candidate["key"]),
            knowledge_type=candidate["knowledge_type"],
            status=KnowledgeStatus.VERIFIED,
            scope_paths=tuple(candidate["related_paths"]),
            summary=str(candidate["statement"]),
            evidence_payloads=(candidate["evidence"],),
            source_type=KnowledgeSourceType.GOVERNANCE_AUDIT,
        )
        return GovernanceMemoryWritebackResult(
            knowledge_id=knowledge.id,
            category=str(candidate["category"]),
            statement=knowledge.summary,
        )

    def _candidate(self, decision: GovernanceDecision) -> dict[str, Any] | None:
        if decision.status != GovernanceDecisionStatus.ACTIVE:
            return None
        if _is_disposable(decision.reason_summary):
            return None

        evidence = _json_object(decision.evidence_json)
        matched_rules = tuple(str(item) for item in evidence.get("matched_rules", ()) if str(item))
        if not matched_rules:
            return None

        task = self.session.get(ChangeTask, decision.task_id)
        if task is None:
            return None
        proposal = self._proposal(decision)
        if proposal is None:
            return None

        related_paths = tuple(
            sorted(
                {
                    path
                    for path in _paths_from_json(decision.allowed_scope_json)
                    + _paths_from_json(decision.denied_scope_json)
                    if path
                }
            )
        )
        category, knowledge_type = _category(decision)
        statement = _statement(decision, matched_rules)
        source = {
            "sourceTaskId": decision.task_id,
            "sourceProposalId": proposal.id,
            "sourceGovernanceDecisionId": decision.id,
            "category": category,
            "statement": statement,
            "reason": decision.reason_summary,
            "evidence": {
                "matchedRules": matched_rules,
                "decision": decision.decision,
                "riskLevel": decision.risk_level,
                "approvalRequired": decision.approval_required,
                "ruleSetVersion": decision.rule_set_version,
                "revision": decision.revision,
            },
            "relatedPaths": related_paths,
            "freshness": "fresh",
            "confidence": "verified",
        }
        return {
            "project_id": task.project_id,
            "key": f"governance:{decision.id}",
            "category": category,
            "knowledge_type": knowledge_type,
            "related_paths": related_paths,
            "statement": statement,
            "evidence": source,
        }

    def _proposal(self, decision: GovernanceDecision) -> ChangeProposal | None:
        if decision.impact_report is not None:
            return self.session.get(ChangeProposal, decision.impact_report.proposal_id)
        return None


def _category(decision: GovernanceDecision) -> tuple[str, KnowledgeType]:
    if decision.decision == "BLOCK":
        return "confirmed_safety_risk", KnowledgeType.CONSTRAINT
    if decision.approval_required:
        return "reusable_engineering_constraint", KnowledgeType.CONSTRAINT
    return "important_engineering_decision", KnowledgeType.DECISION


def _statement(decision: GovernanceDecision, matched_rules: tuple[str, ...]) -> str:
    rules = ", ".join(matched_rules)
    return f"Governance {decision.decision} from {rules}: {decision.reason_summary}"


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _paths_from_json(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if isinstance(data, list):
        return tuple(str(item).replace("\\", "/") for item in data)
    return ()


def _is_disposable(reason: str) -> bool:
    lowered = reason.lower()
    return any(
        re.search(pattern, lowered)
        for pattern in (
            r"\bprovider\b",
            r"\btimeout\b",
            r"\bnetwork\b",
            r"\btemporarygrant\b",
            r"\btemporary\b",
            r"\bdisposable\b",
            r"\bunverified\b",
        )
    )
