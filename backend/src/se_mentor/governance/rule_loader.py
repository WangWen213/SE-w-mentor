from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from se_mentor.governance.rule_repository import RuleDefinition, RuleRepository
from se_mentor.models.governance import GovernanceRule, GovernanceRuleEffect

_EFFECT_STRENGTH = {
    GovernanceRuleEffect.ALLOW: 0,
    GovernanceRuleEffect.REQUIRE_APPROVAL: 1,
    GovernanceRuleEffect.DENY_HARD: 2,
}


class RuleLoadStatus(StrEnum):
    OK = "OK"
    INVALID_CONFIG = "INVALID_CONFIG"


@dataclass(frozen=True)
class RuleSnapshotEntry:
    key: str
    effect: GovernanceRuleEffect
    source: str
    version: int
    reason: str


@dataclass(frozen=True)
class RuleSetSnapshot:
    status: RuleLoadStatus
    can_start_task: bool
    task_id: str | None
    rules: tuple[RuleSnapshotEntry, ...] = ()
    version_hash: str = ""
    errors: tuple[str, ...] = ()


class RuleSetLoader:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_task(
        self,
        *,
        project_id: str,
        task_id: str,
        profile_rules: tuple[RuleDefinition, ...],
    ) -> RuleSetSnapshot:
        validation = self.validate_definitions(profile_rules)
        if validation.status is RuleLoadStatus.INVALID_CONFIG:
            return validation
        repo = RuleRepository(self.session)
        merged = self._merge((*repo.enabled_for_project(project_id), *profile_rules))
        entries = tuple(
            RuleSnapshotEntry(
                key=rule.rule_key if isinstance(rule, GovernanceRule) else rule.key,
                effect=GovernanceRuleEffect(
                    rule.effect if isinstance(rule, GovernanceRule) else rule.effect
                ),
                source=str(rule.scope_type if isinstance(rule, GovernanceRule) else rule.scope),
                version=rule.rule_version if isinstance(rule, GovernanceRule) else rule.version,
                reason=rule.reason,
            )
            for rule in merged
        )
        payload = json.dumps([entry.__dict__ for entry in entries], sort_keys=True, default=str)
        return RuleSetSnapshot(
            status=RuleLoadStatus.OK,
            can_start_task=True,
            task_id=task_id,
            rules=entries,
            version_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    def validate_definitions(self, definitions: tuple[RuleDefinition, ...]) -> RuleSetSnapshot:
        errors: list[str] = []
        for definition in definitions:
            for pattern in definition.patterns:
                if not _valid_glob(pattern):
                    errors.append(f"invalid pattern for {definition.key}: {pattern}")
            if not isinstance(definition.conditions, dict):
                errors.append(f"invalid condition for {definition.key}")
        if errors:
            return RuleSetSnapshot(RuleLoadStatus.INVALID_CONFIG, False, None, errors=tuple(errors))
        return RuleSetSnapshot(RuleLoadStatus.OK, True, None)

    def _merge(
        self,
        rules: tuple[GovernanceRule | RuleDefinition, ...],
    ) -> tuple[GovernanceRule | RuleDefinition, ...]:
        by_key: dict[str, GovernanceRule | RuleDefinition] = {}
        for rule in rules:
            key = rule.rule_key if isinstance(rule, GovernanceRule) else rule.key
            current = by_key.get(key)
            if current is None or _stronger(rule, current):
                by_key[key] = rule
        return tuple(sorted(by_key.values(), key=lambda rule: _sort_key(rule)))


def _stronger(
    left: GovernanceRule | RuleDefinition, right: GovernanceRule | RuleDefinition
) -> bool:
    left_effect = GovernanceRuleEffect(left.effect)
    right_effect = GovernanceRuleEffect(right.effect)
    left_strength = _EFFECT_STRENGTH[left_effect]
    right_strength = _EFFECT_STRENGTH[right_effect]
    if left_strength != right_strength:
        return left_strength > right_strength
    left_priority = left.priority
    right_priority = right.priority
    return left_priority > right_priority


def _sort_key(rule: GovernanceRule | RuleDefinition) -> tuple[int, str]:
    key = rule.rule_key if isinstance(rule, GovernanceRule) else rule.key
    return (-_EFFECT_STRENGTH[GovernanceRuleEffect(rule.effect)], key)


def _valid_glob(pattern: str) -> bool:
    try:
        fnmatch.translate(pattern)
    except re.error:
        return False
    return pattern.count("[") == pattern.count("]")
