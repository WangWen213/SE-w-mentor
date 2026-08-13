"""Task evaluation projection.

Revision ID: 0110_task_evaluations
Revises: 0100_audit_alert
Create Date: 2026-08-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0110_task_evaluations"
down_revision = "0100_audit_alert"
branch_labels = None
depends_on = None

EVALUATION_STATUSES = ("COMPLETED", "PARTIAL", "FAILED")


def upgrade() -> None:
    op.create_table(
        "task_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN {_quoted_values(EVALUATION_STATUSES)}",
            name="status_values",
        ),
        sa.CheckConstraint("length(trim(summary_json)) > 0", name="summary_non_empty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_task_evaluations_task_id"),
    )
    op.create_index("ix_task_evaluations_project_id", "task_evaluations", ["project_id"])
    op.create_index("ix_task_evaluations_task_id", "task_evaluations", ["task_id"])
    op.create_index(
        "ix_task_evaluations_project_created",
        "task_evaluations",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_evaluations_project_created", table_name="task_evaluations")
    op.drop_index("ix_task_evaluations_task_id", table_name="task_evaluations")
    op.drop_index("ix_task_evaluations_project_id", table_name="task_evaluations")
    op.drop_table("task_evaluations")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
