"""Validation, feedback, and progress persistence.

Revision ID: 0070_validation_feedback
Revises: 0060_execution_transaction
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070_validation_feedback"
down_revision = "0060_execution_transaction"
branch_labels = None
depends_on = None

PLAN_STATUSES = ("ACTIVE", "SUPERSEDED", "EXPIRED")
VALIDATION_TYPES = ("TEST", "LINT", "TYPE_CHECK", "MIGRATION", "MANUAL")
RUN_STATUSES = ("PASSED", "FAILED", "ERROR", "SKIPPED", "INCONCLUSIVE")
FEEDBACK_KINDS = ("VALIDATION", "GOVERNANCE", "TOOL", "PROGRESS")
FEEDBACK_SEVERITIES = ("INFO", "WARNING", "ERROR")
EVENT_TYPES = (
    "TASK_CREATED",
    "ACTION_PARSED",
    "GOVERNANCE_DECIDED",
    "TOOL_EXECUTED",
    "VALIDATION_RECORDED",
)


def upgrade() -> None:
    op.create_table(
        "validation_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("execution_policy_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("required_checks_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(f"status IN {_quoted_values(PLAN_STATUSES)}", name="status_values"),
        sa.CheckConstraint(
            "length(trim(required_checks_json)) > 0",
            name="required_checks_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["execution_policy_id"], ["execution_policies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["change_proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_plans_task_id", "validation_plans", ["task_id"])
    op.create_index("ix_validation_plans_proposal_id", "validation_plans", ["proposal_id"])
    op.create_index(
        "ix_validation_plans_execution_policy_id",
        "validation_plans",
        ["execution_policy_id"],
    )
    op.create_index(
        "ix_validation_plans_proposal_policy_version",
        "validation_plans",
        ["proposal_id", "execution_policy_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_validation_plans_task_id_status",
        "validation_plans",
        ["task_id", "status"],
    )

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("validation_plan_id", sa.String(length=36), nullable=False),
        sa.Column("run_order", sa.Integer(), nullable=False),
        sa.Column("validation_type", sa.String(length=16), nullable=False),
        sa.Column("command_summary", sa.String(length=2048), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("required_failure", sa.Boolean(), nullable=False),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("log_artifact_ref", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("run_order >= 1", name="run_order_positive"),
        sa.CheckConstraint(
            f"validation_type IN {_quoted_values(VALIDATION_TYPES)}",
            name="validation_type_values",
        ),
        sa.CheckConstraint(f"status IN {_quoted_values(RUN_STATUSES)}", name="status_values"),
        sa.CheckConstraint("exit_code IS NULL OR exit_code >= 0", name="exit_code_non_negative"),
        sa.CheckConstraint("length(trim(command_summary)) > 0", name="command_summary_non_empty"),
        sa.CheckConstraint("length(trim(log_artifact_ref)) > 0", name="log_artifact_ref_non_empty"),
        sa.CheckConstraint(
            "status != 'PASSED' OR (exit_code = 0 AND required_failure = 0)",
            name="passed_requires_zero_exit_no_required_failure",
        ),
        sa.ForeignKeyConstraint(
            ["validation_plan_id"], ["validation_plans.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_runs_validation_plan_id", "validation_runs", ["validation_plan_id"]
    )
    op.create_index(
        "ix_validation_runs_plan_order",
        "validation_runs",
        ["validation_plan_id", "run_order"],
        unique=True,
    )

    op.create_table(
        "feedback_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=2048), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN {_quoted_values(FEEDBACK_KINDS)}", name="kind_values"),
        sa.CheckConstraint(
            f"severity IN {_quoted_values(FEEDBACK_SEVERITIES)}",
            name="severity_values",
        ),
        sa.CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_signals_task_id", "feedback_signals", ["task_id"])
    op.create_index(
        "ix_feedback_signals_task_id_kind",
        "feedback_signals",
        ["task_id", "kind"],
    )

    op.create_table(
        "progress_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=2048), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"event_type IN {_quoted_values(EVENT_TYPES)}", name="event_type_values"
        ),
        sa.CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_progress_events_task_id", "progress_events", ["task_id"])
    op.create_index(
        "ix_progress_events_task_id_event_type",
        "progress_events",
        ["task_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_progress_events_task_id_event_type", table_name="progress_events")
    op.drop_index("ix_progress_events_task_id", table_name="progress_events")
    op.drop_table("progress_events")
    op.drop_index("ix_feedback_signals_task_id_kind", table_name="feedback_signals")
    op.drop_index("ix_feedback_signals_task_id", table_name="feedback_signals")
    op.drop_table("feedback_signals")
    op.drop_index("ix_validation_runs_plan_order", table_name="validation_runs")
    op.drop_index("ix_validation_runs_validation_plan_id", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index("ix_validation_plans_task_id_status", table_name="validation_plans")
    op.drop_index("ix_validation_plans_proposal_policy_version", table_name="validation_plans")
    op.drop_index("ix_validation_plans_execution_policy_id", table_name="validation_plans")
    op.drop_index("ix_validation_plans_proposal_id", table_name="validation_plans")
    op.drop_index("ix_validation_plans_task_id", table_name="validation_plans")
    op.drop_table("validation_plans")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
