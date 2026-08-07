from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, exc, inspect, text

from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    GovernanceRule,
    GovernanceRuleEffect,
    GovernanceRuleHit,
    GovernanceRuleScope,
    GovernanceVerdict,
    ImpactReport,
    ImpactReportStatus,
)
from se_mentor.models.llm import RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskStatus,
)

PROPOSAL_HASH = "a" * 64
REVISION = "b10997f"


def test_T012_deny_hard_rule_cannot_be_overridable(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "governance-rule.sqlite3")
    session_factory = create_session_factory(engine)
    project_id, _task_id, _proposal_id = _insert_project_task_proposal(session_factory, tmp_path)

    with session_scope(session_factory) as session:
        rule = GovernanceRule(
            project_id=project_id,
            rule_key="protect-secrets",
            rule_name="Protect credential sinks",
            scope_type=GovernanceRuleScope.PROJECT,
            effect=GovernanceRuleEffect.DENY_HARD,
            priority=10,
            patterns_json='["*.env", "credentials"]',
            conditions_json='{"contains_secret_sink": true}',
            reason="Never persist plaintext secrets.",
            overridable=False,
            enabled=True,
            rule_version=1,
        )
        session.add(rule)
        session.flush()
        rule_id = rule.id

    with session_scope(session_factory) as session:
        reloaded = session.get(GovernanceRule, rule_id)

    assert reloaded is not None
    assert reloaded.effect == GovernanceRuleEffect.DENY_HARD
    assert reloaded.overridable is False
    assert reloaded.rule_key == "protect-secrets"
    assert reloaded.rule_version == 1

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO governance_rules (
                id, project_id, rule_key, rule_name, scope_type, effect, priority,
                patterns_json, conditions_json, reason, overridable, enabled,
                rule_version, created_at
            )
            VALUES (
                'bad-deny-override', :project_id, 'protect-secrets', 'bad',
                'PROJECT', 'DENY_HARD', 1, '[]', '{}', 'bad', 1, 1,
                2, CURRENT_TIMESTAMP
            )
            """,
            {"project_id": project_id},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO governance_rules (
                id, rule_key, rule_name, scope_type, effect, priority,
                patterns_json, conditions_json, reason, overridable, enabled,
                rule_version, created_at
            )
            VALUES (
                'bad-effect', 'bad-effect', 'bad', 'SYSTEM', 'NOT_AN_EFFECT', -1,
                '[]', '{}', 'bad', 0, 1, 0, CURRENT_TIMESTAMP
            )
            """,
            {},
        )

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            GovernanceRule(
                rule_key="protect-secrets",
                rule_name="Duplicate version",
                scope_type=GovernanceRuleScope.SYSTEM,
                effect=GovernanceRuleEffect.ALLOW,
                priority=20,
                patterns_json="[]",
                conditions_json="{}",
                reason="duplicate version",
                overridable=True,
                enabled=True,
                rule_version=1,
            )
        )


def test_T012_rule_hit_requires_existing_rule_and_retains_version(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "rule-hit.sqlite3")
    session_factory = create_session_factory(engine)
    project_id, task_id, proposal_id = _insert_project_task_proposal(session_factory, tmp_path)
    rule_v1_id = _insert_rule(session_factory, project_id, version=1)
    impact_report_id = _insert_impact_report(session_factory, task_id, proposal_id)
    decision_id = _insert_decision(session_factory, task_id, impact_report_id)

    with session_scope(session_factory) as session:
        hit = GovernanceRuleHit(
            decision_id=decision_id,
            rule_id=rule_v1_id,
            rule_version=1,
            effect=GovernanceRuleEffect.DENY_HARD,
            matched_evidence_json='[{"source":"backend/src","summary":"secret sink"}]',
        )
        session.add(hit)
        session.flush()
        hit_id = hit.id

    with session_scope(session_factory) as session:
        reloaded = session.get(GovernanceRuleHit, hit_id)
        assert reloaded is not None
        assert reloaded.rule is not None
        assert reloaded.rule.rule_version == 1
        assert reloaded.decision is not None
        assert reloaded.effect == GovernanceRuleEffect.DENY_HARD

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO governance_rule_hits (
                id, decision_id, rule_id, rule_version, effect,
                matched_evidence_json, created_at
            )
            VALUES (
                'missing-rule-hit', :decision_id, 'missing-rule', 1, 'DENY_HARD',
                '[{"source":"missing","summary":"bad"}]', CURRENT_TIMESTAMP
            )
            """,
            {"decision_id": decision_id},
        )

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            GovernanceRuleHit(
                decision_id=decision_id,
                rule_id=rule_v1_id,
                rule_version=1,
                effect=GovernanceRuleEffect.DENY_HARD,
                matched_evidence_json='[{"source":"duplicate","summary":"bad"}]',
            )
        )


def test_T012_impact_report_and_decision_bind_evidence_revision_and_hash(
    tmp_path: Path,
) -> None:
    engine = _create_schema(tmp_path / "decision.sqlite3")
    session_factory = create_session_factory(engine)
    project_id, task_id, proposal_id = _insert_project_task_proposal(session_factory, tmp_path)
    rule_v1_id = _insert_rule(session_factory, project_id, version=1)
    impact_report_id = _insert_impact_report(session_factory, task_id, proposal_id)

    with session_scope(session_factory) as session:
        decision = GovernanceDecision(
            task_id=task_id,
            impact_report_id=impact_report_id,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            decision=GovernanceVerdict.BLOCK,
            risk_level=RiskLevel.CRITICAL,
            reason_summary="DENY_HARD rule matched credential persistence risk.",
            allowed_scope_json="[]",
            denied_scope_json='["credential persistence"]',
            approval_required=True,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version="governance-ruleset-v1",
            evidence_json='[{"source":"evidence://T012","summary":"rule hit"}]',
        )
        session.add(decision)
        session.flush()
        session.add(
            GovernanceRuleHit(
                decision_id=decision.id,
                rule_id=rule_v1_id,
                rule_version=1,
                effect=GovernanceRuleEffect.DENY_HARD,
                matched_evidence_json='[{"source":"backend/src","summary":"hit"}]',
            )
        )
        decision_id = decision.id

    with session_scope(session_factory) as session:
        reloaded = session.get(GovernanceDecision, decision_id)
        assert reloaded is not None
        assert reloaded.proposal_hash == PROPOSAL_HASH
        assert reloaded.revision == REVISION
        assert reloaded.rule_set_version == "governance-ruleset-v1"
        assert reloaded.evidence_json == '[{"source":"evidence://T012","summary":"rule hit"}]'
        assert reloaded.impact_report is not None
        assert reloaded.impact_report.proposal_id == proposal_id
        assert reloaded.rule_hits[0].rule_version == 1

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO governance_decisions (
                id, task_id, proposal_hash, revision, decision, risk_level,
                reason_summary, approval_required, status, rule_set_version,
                evidence_json, created_at
            )
            VALUES (
                'bad-decision', :task_id, 'too-short', '', 'ALLOW', 'LOW',
                'bad', 0, 'ACTIVE', 'ruleset', '', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": task_id},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO impact_reports (
                id, task_id, proposal_id, direct_impacts_json, evidence_json,
                status, created_at
            )
            VALUES (
                'bad-impact', :task_id, 'missing-proposal', '[]', '[]',
                'CURRENT', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": task_id},
        )


def test_T012_decision_history_keeps_exact_rule_version_after_new_rule_version(
    tmp_path: Path,
) -> None:
    engine = _create_schema(tmp_path / "history.sqlite3")
    session_factory = create_session_factory(engine)
    project_id, task_id, proposal_id = _insert_project_task_proposal(session_factory, tmp_path)
    rule_v1_id = _insert_rule(session_factory, project_id, version=1)
    impact_report_id = _insert_impact_report(session_factory, task_id, proposal_id)
    first_decision_id = _insert_decision(session_factory, task_id, impact_report_id)

    with session_scope(session_factory) as session:
        session.add(
            GovernanceRuleHit(
                decision_id=first_decision_id,
                rule_id=rule_v1_id,
                rule_version=1,
                effect=GovernanceRuleEffect.DENY_HARD,
                matched_evidence_json='[{"source":"v1","summary":"hit"}]',
            )
        )

    rule_v2_id = _insert_rule(session_factory, project_id, version=2)
    second_decision_id = _insert_decision(
        session_factory,
        task_id,
        impact_report_id,
        proposal_hash="b" * 64,
        revision="next-revision",
        rule_set_version="governance-ruleset-v2",
    )

    with session_scope(session_factory) as session:
        session.add(
            GovernanceRuleHit(
                decision_id=second_decision_id,
                rule_id=rule_v2_id,
                rule_version=2,
                effect=GovernanceRuleEffect.DENY_HARD,
                matched_evidence_json='[{"source":"v2","summary":"hit"}]',
            )
        )

    with session_scope(session_factory) as session:
        first = session.get(GovernanceDecision, first_decision_id)
        second = session.get(GovernanceDecision, second_decision_id)
        assert first is not None
        assert second is not None
        assert first.proposal_hash == PROPOSAL_HASH
        assert first.revision == REVISION
        assert first.rule_hits[0].rule_version == 1
        assert first.rule_hits[0].rule.id == rule_v1_id
        assert second.rule_hits[0].rule_version == 2
        assert second.rule_hits[0].rule.id == rule_v2_id


def test_T012_governance_schema_indexes_and_migration_match_the_orm(tmp_path: Path) -> None:
    orm_engine = _create_schema(tmp_path / "orm.sqlite3")
    migrated_engine = _create_migrated_schema(tmp_path / "migrated.sqlite3")

    for engine in (orm_engine, migrated_engine):
        inspector = inspect(engine)
        assert {
            "impact_reports",
            "governance_decisions",
            "governance_rules",
            "governance_rule_hits",
        }.issubset(inspector.get_table_names())
        assert {
            "ix_governance_rules_project_id",
            "ix_governance_rules_rule_key_rule_version",
            "ix_governance_rules_effect",
            "ix_governance_rules_priority",
        }.issubset(_index_names(engine, "governance_rules"))
        assert {
            "ix_governance_rule_hits_decision_id",
            "ix_governance_rule_hits_rule_id_rule_version",
        }.issubset(_index_names(engine, "governance_rule_hits"))
        assert {
            "ix_impact_reports_task_id",
            "ix_impact_reports_proposal_id",
            "ix_impact_reports_status",
        }.issubset(_index_names(engine, "impact_reports"))
        assert {
            "ix_governance_decisions_task_id",
            "ix_governance_decisions_action_id",
            "ix_governance_decisions_impact_report_id",
            "ix_governance_decisions_proposal_hash",
            "ix_governance_decisions_status",
        }.issubset(_index_names(engine, "governance_decisions"))
        assert {
            "ck_governance_rules_effect_values",
            "ck_governance_rules_priority_non_negative",
            "ck_governance_rules_rule_version_positive",
            "ck_governance_rules_deny_hard_not_overridable",
        }.issubset(_check_constraint_names(engine, "governance_rules"))
        assert {
            "ck_governance_decisions_proposal_hash_length",
            "ck_governance_decisions_revision_non_empty",
            "ck_governance_decisions_decision_values",
            "ck_governance_decisions_status_values",
        }.issubset(_check_constraint_names(engine, "governance_decisions"))
        assert _foreign_key_ondelete(engine, "governance_rules", "project_id") == "RESTRICT"
        assert _foreign_key_ondelete(engine, "impact_reports", "proposal_id") == "RESTRICT"
        assert (
            _foreign_key_ondelete(engine, "governance_decisions", "impact_report_id") == "RESTRICT"
        )
        assert _foreign_key_ondelete(engine, "governance_rule_hits", "decision_id") == "RESTRICT"

    assert _column_names(orm_engine, "governance_rules") == _column_names(
        migrated_engine,
        "governance_rules",
    )
    assert _column_names(orm_engine, "governance_decisions") == _column_names(
        migrated_engine,
        "governance_decisions",
    )

    backend_dir = Path(__file__).resolve().parents[2]
    migration_text = (backend_dir / "migrations/versions/0040_governance.py").read_text(
        encoding="utf-8"
    )
    for expected_fragment in (
        'revision = "0040_governance"',
        'down_revision = "0030_llm_action"',
        "deny_hard_not_overridable",
        "proposal_hash_length",
    ):
        assert expected_fragment in migration_text


def test_T012_governance_tables_do_not_add_secret_or_unbounded_dump_sinks(
    tmp_path: Path,
) -> None:
    engine = _create_schema(tmp_path / "audit-safety.sqlite3")
    forbidden_column_names = {
        "api_key",
        "token_secret",
        "provider_secret",
        "authorization_header",
        "raw_headers",
        "credentials",
        "password",
        "secret",
        "prompt",
        "response",
        "raw_prompt",
        "raw_response",
        "conversation",
        "raw_log",
        "full_log",
        "source_dump",
        "source_code",
    }

    for table_name in (
        "impact_reports",
        "governance_decisions",
        "governance_rules",
        "governance_rule_hits",
    ):
        assert _column_names(engine, table_name).isdisjoint(forbidden_column_names)


def _create_schema(database_path: Path) -> Engine:
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    return engine


def _create_migrated_schema(database_path: Path) -> Engine:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    config.set_main_option("prepend_sys_path", str(backend_dir / "src"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_sqlite_engine(f"sqlite:///{database_path}")


def _insert_project_task_proposal(
    session_factory: Any,
    tmp_path: Path,
) -> tuple[str, str, str]:
    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Persist governance domain facts.",
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        proposal = ChangeProposal(
            task_id=task.id,
            version=1,
            goal="Persist governance facts.",
            expected_behavior="Governance records remain auditable.",
            initial_scope_json='["backend/src/se_mentor/models/governance.py"]',
            acceptance_criteria_json='["decision history is immutable"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.CONFIRMED,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        session.add(proposal)
        session.flush()
        return project.id, task.id, proposal.id


def _insert_rule(session_factory: Any, project_id: str, *, version: int) -> str:
    with session_scope(session_factory) as session:
        rule = GovernanceRule(
            project_id=project_id,
            rule_key="protect-secrets",
            rule_name="Protect credential sinks",
            scope_type=GovernanceRuleScope.PROJECT,
            effect=GovernanceRuleEffect.DENY_HARD,
            priority=10,
            patterns_json='["*.env", "credentials"]',
            conditions_json='{"contains_secret_sink": true}',
            reason=f"Secret safety rule v{version}.",
            overridable=False,
            enabled=True,
            rule_version=version,
        )
        session.add(rule)
        session.flush()
        return rule.id


def _insert_impact_report(session_factory: Any, task_id: str, proposal_id: str) -> str:
    with session_scope(session_factory) as session:
        report = ImpactReport(
            task_id=task_id,
            proposal_id=proposal_id,
            base_revision=REVISION,
            direct_impacts_json='[{"path":"backend/src","kind":"model"}]',
            indirect_impacts_json="[]",
            api_impacts_json="[]",
            database_impacts_json='[{"table":"governance_rules"}]',
            test_impacts_json='["backend/tests/models/test_governance_models.py"]',
            deployment_impacts_json="[]",
            uncertainties_json="[]",
            evidence_json='[{"source":"SPEC.problem-statement.md","summary":"governance schema"}]',
            status=ImpactReportStatus.CURRENT,
        )
        session.add(report)
        session.flush()
        return report.id


def _insert_decision(
    session_factory: Any,
    task_id: str,
    impact_report_id: str,
    *,
    proposal_hash: str = PROPOSAL_HASH,
    revision: str = REVISION,
    rule_set_version: str = "governance-ruleset-v1",
) -> str:
    with session_scope(session_factory) as session:
        decision = GovernanceDecision(
            task_id=task_id,
            impact_report_id=impact_report_id,
            proposal_hash=proposal_hash,
            revision=revision,
            decision=GovernanceVerdict.BLOCK,
            risk_level=RiskLevel.CRITICAL,
            reason_summary="DENY_HARD rule matched.",
            allowed_scope_json="[]",
            denied_scope_json='["credential persistence"]',
            approval_required=True,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version=rule_set_version,
            evidence_json='[{"source":"evidence://governance","summary":"decision"}]',
        )
        session.add(decision)
        session.flush()
        return decision.id


def _execute(engine: Engine, statement: str, parameters: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement), parameters)


def _column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _index_names(engine: Engine, table_name: str) -> set[str]:
    return {
        name
        for index in inspect(engine).get_indexes(table_name)
        if (name := index["name"]) is not None
    }


def _check_constraint_names(engine: Engine, table_name: str) -> set[str]:
    return {
        name
        for constraint in inspect(engine).get_check_constraints(table_name)
        if (name := constraint["name"]) is not None
    }


def _foreign_key_ondelete(engine: Engine, table_name: str, constrained_column: str) -> str:
    for foreign_key in inspect(engine).get_foreign_keys(table_name):
        if foreign_key["constrained_columns"] == [constrained_column]:
            return str(foreign_key["options"].get("ondelete"))
    raise AssertionError(f"missing foreign key for {table_name}.{constrained_column}")
