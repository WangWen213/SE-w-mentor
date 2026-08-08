"""Audit, alert, and retention persistence.

Revision ID: 0100_audit_alert
Revises: 0090_code_index
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0100_audit_alert"
down_revision = "0090_code_index"
branch_labels = None
depends_on = None

ACTOR_TYPES = ("SYSTEM", "USER", "AGENT", "TOOL")
EVENT_TYPES = (
    "TASK_CREATED",
    "ACTION_PARSED",
    "GOVERNANCE_DECIDED",
    "TOOL_EXECUTED",
    "VALIDATION_RECORDED",
)
ALERT_SEVERITIES = ("INFO", "WARNING", "HIGH", "CRITICAL")
ALERT_STATUSES = ("OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED")


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload_summary", sa.String(length=2048), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"actor_type IN {_quoted_values(ACTOR_TYPES)}", name="actor_type_values"
        ),
        sa.CheckConstraint(
            f"event_type IN {_quoted_values(EVENT_TYPES)}", name="event_type_values"
        ),
        sa.CheckConstraint("length(trim(correlation_id)) > 0", name="correlation_id_non_empty"),
        sa.CheckConstraint("length(trim(actor_id)) > 0", name="actor_id_non_empty"),
        sa.CheckConstraint(
            "length(trim(payload_summary)) > 0",
            name="payload_summary_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_task_id", "audit_events", ["task_id"])
    op.create_index("ix_audit_events_task_id_created_at", "audit_events", ["task_id", "created_at"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events are append-only');
        END
        """
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("system_scope", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=2048), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"severity IN {_quoted_values(ALERT_SEVERITIES)}",
            name="severity_values",
        ),
        sa.CheckConstraint(f"status IN {_quoted_values(ALERT_STATUSES)}", name="status_values"),
        sa.CheckConstraint("task_id IS NOT NULL OR system_scope = 1", name="task_or_system_scope"),
        sa.CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_task_id", "alert_events", ["task_id"])
    op.create_index("ix_alert_events_task_id_status", "alert_events", ["task_id", "status"])
    op.create_index("ix_alert_events_severity_status", "alert_events", ["severity", "status"])


def downgrade() -> None:
    op.drop_index("ix_alert_events_severity_status", table_name="alert_events")
    op.drop_index("ix_alert_events_task_id_status", table_name="alert_events")
    op.drop_index("ix_alert_events_task_id", table_name="alert_events")
    op.drop_table("alert_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_index("ix_audit_events_task_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_task_id", table_name="audit_events")
    op.drop_table("audit_events")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
