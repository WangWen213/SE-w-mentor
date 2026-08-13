from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.governance import GovernanceRule, GovernanceRuleEffect, GovernanceRuleScope


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    name: str
    scope: GovernanceRuleScope
    effect: GovernanceRuleEffect
    priority: int
    patterns: tuple[str, ...]
    conditions: dict[str, object]
    reason: str
    overridable: bool
    project_id: str | None = None
    enabled: bool = True
    version: int = 1


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, definition: RuleDefinition) -> GovernanceRule:
        rule = GovernanceRule(
            project_id=definition.project_id,
            rule_key=definition.key,
            rule_name=definition.name,
            scope_type=definition.scope,
            effect=definition.effect,
            priority=definition.priority,
            patterns_json=json.dumps(definition.patterns),
            conditions_json=json.dumps(definition.conditions, sort_keys=True),
            reason=definition.reason,
            overridable=definition.overridable,
            enabled=definition.enabled,
            rule_version=definition.version,
        )
        self.session.add(rule)
        self.session.flush()
        return rule

    def enabled_for_project(self, project_id: str) -> tuple[GovernanceRule, ...]:
        rows = self.session.scalars(
            select(GovernanceRule).where(
                GovernanceRule.enabled.is_(True),
                (GovernanceRule.project_id.is_(None)) | (GovernanceRule.project_id == project_id),
            )
        ).all()
        return tuple(rows)
