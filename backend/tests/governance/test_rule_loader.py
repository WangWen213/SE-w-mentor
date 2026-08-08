from __future__ import annotations

from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.governance.rule_loader import RuleLoadStatus, RuleSetLoader
from se_mentor.governance.rule_repository import RuleDefinition, RuleRepository
from se_mentor.models.governance import GovernanceRuleEffect, GovernanceRuleScope


def test_T044_project_rule_cannot_disable_system_deny_hard(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "rules.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        repo = RuleRepository(session)
        repo.add(
            RuleDefinition(
                key="protect-secrets",
                name="Protect secrets",
                scope=GovernanceRuleScope.SYSTEM,
                effect=GovernanceRuleEffect.DENY_HARD,
                priority=100,
                patterns=("*.env", "*secret*"),
                conditions={"path": True},
                reason="Secrets are protected.",
                overridable=False,
            )
        )
        repo.add(
            RuleDefinition(
                key="protect-secrets",
                name="Project attempts to allow secrets",
                scope=GovernanceRuleScope.PROJECT,
                effect=GovernanceRuleEffect.ALLOW,
                priority=1,
                patterns=("*.env",),
                conditions={"path": True},
                reason="Project relaxation.",
                overridable=True,
                project_id=ids["project_id"],
                version=2,
            )
        )
        loader = RuleSetLoader(session)
        snapshot = loader.for_task(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            profile_rules=(),
        )
        invalid = loader.validate_definitions(
            (
                RuleDefinition(
                    key="bad",
                    name="bad",
                    scope=GovernanceRuleScope.SYSTEM,
                    effect=GovernanceRuleEffect.REQUIRE_APPROVAL,
                    priority=1,
                    patterns=("[",),
                    conditions={"path": True},
                    reason="bad glob",
                    overridable=True,
                ),
            )
        )

    assert snapshot.status is RuleLoadStatus.OK
    assert snapshot.task_id == ids["task_id"]
    assert snapshot.version_hash
    assert len(snapshot.rules) == 1
    assert snapshot.rules[0].key == "protect-secrets"
    assert snapshot.rules[0].effect is GovernanceRuleEffect.DENY_HARD
    assert snapshot.rules[0].source == "SYSTEM"
    assert invalid.status is RuleLoadStatus.INVALID_CONFIG
    assert invalid.can_start_task is False
    assert "invalid pattern" in invalid.errors[0]
