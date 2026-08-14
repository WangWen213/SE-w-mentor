from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
from time import perf_counter

from sqlalchemy.orm import Session

from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    GovernanceRuleEffect,
    GovernanceVerdict,
)
from se_mentor.models.llm import RiskLevel
from se_mentor.paths import canonical_project_paths

LOGGER = logging.getLogger("se_mentor.governance.decision_service")


class GovernanceDecisionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        *,
        task_id: str,
        action_id: str | None,
        proposal_hash: str,
        revision: str,
        rules: tuple[RuleDefinition, ...],
        changed_paths: tuple[str, ...],
        llm_verdict: GovernanceVerdict,
        user_verdict: GovernanceVerdict | None,
    ) -> GovernanceDecision:
        total_started = perf_counter()
        rules_started = perf_counter()
        changed_paths = canonical_project_paths(changed_paths)
        matched = tuple(_matched_rules(rules, changed_paths))
        rules_ms = int((perf_counter() - rules_started) * 1000)
        decision_started = perf_counter()
        deny = tuple(rule for rule in matched if rule.effect == GovernanceRuleEffect.DENY_HARD)
        approval = tuple(
            rule for rule in matched if rule.effect == GovernanceRuleEffect.REQUIRE_APPROVAL
        )
        if deny:
            decision = GovernanceVerdict.BLOCK
            risk = RiskLevel.CRITICAL
            approval_required = False
            reason = deny[0].reason
            allowed_scope: tuple[str, ...] = ()
            denied_scope = changed_paths
        elif approval or user_verdict == GovernanceVerdict.WARN:
            decision = GovernanceVerdict.WARN
            risk = RiskLevel.MEDIUM
            approval_required = True
            reason = approval[0].reason if approval else "User warning requires approval."
            allowed_scope = changed_paths
            denied_scope = ()
        elif llm_verdict == GovernanceVerdict.BLOCK or user_verdict == GovernanceVerdict.BLOCK:
            decision = GovernanceVerdict.BLOCK
            risk = RiskLevel.HIGH
            approval_required = False
            reason = "Requested block verdict."
            allowed_scope = ()
            denied_scope = changed_paths
        else:
            decision = GovernanceVerdict.ALLOW
            risk = RiskLevel.LOW
            approval_required = False
            reason = "Allowed within finite changed path scope."
            allowed_scope = changed_paths
            denied_scope = ()
        decision_ms = int((perf_counter() - decision_started) * 1000)

        evidence = {
            "matched_rules": [rule.key for rule in matched],
            "llm_verdict": llm_verdict,
            "user_verdict": user_verdict,
            "changed_paths": changed_paths,
        }
        governance_decision = GovernanceDecision(
            task_id=task_id,
            action_id=action_id,
            proposal_hash=proposal_hash,
            revision=revision,
            decision=decision,
            risk_level=risk,
            reason_summary=reason,
            allowed_scope_json=json.dumps(tuple(sorted(allowed_scope))),
            denied_scope_json=json.dumps(tuple(sorted(denied_scope))),
            approval_required=approval_required,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version=_rule_version(matched),
            evidence_json=json.dumps(evidence, sort_keys=True, default=str),
        )
        persist_started = perf_counter()
        self.session.add(governance_decision)
        self.session.flush()
        persist_ms = int((perf_counter() - persist_started) * 1000)
        LOGGER.info(
            (
                "[perf] governance.rules_load task_id=%s duration_ms=%s "
                "rules_count=%s matched_rules=%s changed_paths=%s"
            ),
            task_id,
            rules_ms,
            len(rules),
            len(matched),
            len(changed_paths),
        )
        LOGGER.info(
            (
                "[perf] governance.decision task_id=%s duration_ms=%s "
                "decision=%s risk=%s approval_required=%s"
            ),
            task_id,
            decision_ms,
            decision,
            risk,
            approval_required,
        )
        LOGGER.info(
            ("[perf] governance.persist task_id=%s duration_ms=%s decision_id=%s"),
            task_id,
            persist_ms,
            governance_decision.id,
        )
        LOGGER.info(
            (
                "[perf] governance.total task_id=%s duration_ms=%s "
                "rules_ms=%s decision_ms=%s persist_ms=%s"
            ),
            task_id,
            int((perf_counter() - total_started) * 1000),
            rules_ms,
            decision_ms,
            persist_ms,
        )
        return governance_decision


def _matched_rules(
    rules: tuple[RuleDefinition, ...],
    changed_paths: tuple[str, ...],
) -> tuple[RuleDefinition, ...]:
    matched: list[RuleDefinition] = []
    for rule in sorted(rules, key=lambda item: (-item.priority, item.key)):
        if any(_matches(pattern, changed_paths) for pattern in rule.patterns):
            matched.append(rule)
    return tuple(matched)


def _matches(pattern: str, changed_paths: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) or pattern in path for path in changed_paths)


def _rule_version(rules: tuple[RuleDefinition, ...]) -> str:
    payload = json.dumps(
        [(rule.key, rule.version, rule.effect, rule.priority) for rule in rules],
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
