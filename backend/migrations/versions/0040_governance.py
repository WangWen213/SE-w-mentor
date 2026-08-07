"""Governance domain persistence.

Revision ID: 0040_governance
Revises: 0030_llm_action
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_governance"
down_revision = "0030_llm_action"
branch_labels = None
depends_on = None

IMPACT_REPORT_STATUSES = ("CURRENT", "STALE", "SUPERSEDED")
GOVERNANCE_VERDICTS = ("ALLOW", "WARN", "BLOCK")
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
GOVERNANCE_DECISION_STATUSES = ("ACTIVE", "EXPIRED", "SUPERSEDED")
GOVERNANCE_RULE_SCOPES = ("SYSTEM", "PROJECT", "TASK")
GOVERNANCE_RULE_EFFECTS = ("DENY_HARD", "REQUIRE_APPROVAL", "ALLOW")


def upgrade() -> None:
    op.create_table(
        "impact_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.String(length=64), nullable=True),
        sa.Column("direct_impacts_json", sa.Text(), nullable=False),
        sa.Column("indirect_impacts_json", sa.Text(), nullable=True),
        sa.Column("api_impacts_json", sa.Text(), nullable=True),
        sa.Column("database_impacts_json", sa.Text(), nullable=True),
        sa.Column("test_impacts_json", sa.Text(), nullable=True),
        sa.Column("deployment_impacts_json", sa.Text(), nullable=True),
        sa.Column("uncertainties_json", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN {_quoted_values(IMPACT_REPORT_STATUSES)}",
            name="status_values",
        ),
        sa.CheckConstraint(
            "length(trim(direct_impacts_json)) > 0",
            name="direct_impacts_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["change_proposals.id"],
            name="fk_impact_reports_proposal_id_change_proposals",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_impact_reports_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_impact_reports"),
    )
    op.create_index("ix_impact_reports_task_id", "impact_reports", ["task_id"], unique=False)
    op.create_index(
        "ix_impact_reports_proposal_id", "impact_reports", ["proposal_id"], unique=False
    )
    op.create_index("ix_impact_reports_status", "impact_reports", ["status"], unique=False)

    op.create_table(
        "governance_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("effect", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("patterns_json", sa.Text(), nullable=False),
        sa.Column("conditions_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=2048), nullable=False),
        sa.Column("overridable", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"scope_type IN {_quoted_values(GOVERNANCE_RULE_SCOPES)}",
            name="scope_type_values",
        ),
        sa.CheckConstraint(
            f"effect IN {_quoted_values(GOVERNANCE_RULE_EFFECTS)}",
            name="effect_values",
        ),
        sa.CheckConstraint("priority >= 0", name="priority_non_negative"),
        sa.CheckConstraint("rule_version >= 1", name="rule_version_positive"),
        sa.CheckConstraint("length(trim(rule_key)) > 0", name="rule_key_non_empty"),
        sa.CheckConstraint("length(trim(patterns_json)) > 0", name="patterns_non_empty"),
        sa.CheckConstraint("length(trim(conditions_json)) > 0", name="conditions_non_empty"),
        sa.CheckConstraint(
            "effect != 'DENY_HARD' OR overridable = 0",
            name="deny_hard_not_overridable",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_governance_rules_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_governance_rules"),
        sa.UniqueConstraint("id", "rule_version", name="uq_governance_rules_id_rule_version"),
    )
    op.create_index(
        "ix_governance_rules_project_id",
        "governance_rules",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_rules_rule_key_rule_version",
        "governance_rules",
        ["rule_key", "rule_version"],
        unique=True,
    )
    op.create_index("ix_governance_rules_effect", "governance_rules", ["effect"], unique=False)
    op.create_index("ix_governance_rules_priority", "governance_rules", ["priority"], unique=False)

    op.create_table(
        "governance_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=True),
        sa.Column("impact_report_id", sa.String(length=36), nullable=True),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reason_summary", sa.String(length=2048), nullable=False),
        sa.Column("allowed_scope_json", sa.Text(), nullable=True),
        sa.Column("denied_scope_json", sa.Text(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rule_set_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"decision IN {_quoted_values(GOVERNANCE_VERDICTS)}",
            name="decision_values",
        ),
        sa.CheckConstraint(
            f"risk_level IN {_quoted_values(RISK_LEVELS)}", name="risk_level_values"
        ),
        sa.CheckConstraint(
            f"status IN {_quoted_values(GOVERNANCE_DECISION_STATUSES)}",
            name="status_values",
        ),
        sa.CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        sa.CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        sa.CheckConstraint("length(trim(reason_summary)) > 0", name="reason_summary_non_empty"),
        sa.CheckConstraint(
            "length(trim(rule_set_version)) > 0",
            name="rule_set_version_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["agent_actions.id"],
            name="fk_governance_decisions_action_id_agent_actions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["impact_report_id"],
            ["impact_reports.id"],
            name="fk_governance_decisions_impact_report_id_impact_reports",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_governance_decisions_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_governance_decisions"),
    )
    op.create_index(
        "ix_governance_decisions_task_id",
        "governance_decisions",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_decisions_action_id",
        "governance_decisions",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_decisions_impact_report_id",
        "governance_decisions",
        ["impact_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_decisions_proposal_hash",
        "governance_decisions",
        ["proposal_hash"],
        unique=False,
    )
    op.create_index(
        "ix_governance_decisions_status",
        "governance_decisions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "governance_rule_hits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("effect", sa.String(length=32), nullable=False),
        sa.Column("matched_evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"effect IN {_quoted_values(GOVERNANCE_RULE_EFFECTS)}",
            name="effect_values",
        ),
        sa.CheckConstraint("rule_version >= 1", name="rule_version_positive"),
        sa.CheckConstraint(
            "length(trim(matched_evidence_json)) > 0",
            name="matched_evidence_non_empty",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["governance_decisions.id"],
            name="fk_governance_rule_hits_decision_id_governance_decisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["governance_rules.id", "governance_rules.rule_version"],
            name="fk_governance_rule_hits_rule_version_governance_rules",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_governance_rule_hits"),
    )
    op.create_index(
        "ix_governance_rule_hits_decision_id",
        "governance_rule_hits",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_rule_hits_decision_rule_version",
        "governance_rule_hits",
        ["decision_id", "rule_id", "rule_version"],
        unique=True,
    )
    op.create_index(
        "ix_governance_rule_hits_rule_id_rule_version",
        "governance_rule_hits",
        ["rule_id", "rule_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_rule_hits_rule_id_rule_version", table_name="governance_rule_hits")
    op.drop_index(
        "ix_governance_rule_hits_decision_rule_version", table_name="governance_rule_hits"
    )
    op.drop_index("ix_governance_rule_hits_decision_id", table_name="governance_rule_hits")
    op.drop_table("governance_rule_hits")
    op.drop_index("ix_governance_decisions_status", table_name="governance_decisions")
    op.drop_index("ix_governance_decisions_proposal_hash", table_name="governance_decisions")
    op.drop_index("ix_governance_decisions_impact_report_id", table_name="governance_decisions")
    op.drop_index("ix_governance_decisions_action_id", table_name="governance_decisions")
    op.drop_index("ix_governance_decisions_task_id", table_name="governance_decisions")
    op.drop_table("governance_decisions")
    op.drop_index("ix_governance_rules_priority", table_name="governance_rules")
    op.drop_index("ix_governance_rules_effect", table_name="governance_rules")
    op.drop_index("ix_governance_rules_rule_key_rule_version", table_name="governance_rules")
    op.drop_index("ix_governance_rules_project_id", table_name="governance_rules")
    op.drop_table("governance_rules")
    op.drop_index("ix_impact_reports_status", table_name="impact_reports")
    op.drop_index("ix_impact_reports_proposal_id", table_name="impact_reports")
    op.drop_index("ix_impact_reports_task_id", table_name="impact_reports")
    op.drop_table("impact_reports")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
