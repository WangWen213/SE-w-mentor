"""Task domain persistence.

Revision ID: 0020_task_domain
Revises: 0010_project_domain
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_task_domain"
down_revision = "0010_project_domain"
branch_labels = None
depends_on = None

TASK_STATUSES = (
    "CREATED",
    "WAITING_FOR_LOCK",
    "INITIALIZING",
    "CONTEXT_BUILDING",
    "DECIDING",
    "PROPOSAL_REVIEW",
    "GOVERNING",
    "APPROVAL_REQUIRED",
    "ACTION_PENDING",
    "EXECUTING",
    "VALIDATING",
    "REPAIRING",
    "STAGNATION_WARNING",
    "PAUSED",
    "KNOWLEDGE_UPDATING",
    "ROLLING_BACK",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
)
PROPOSAL_COMPLETENESS_VALUES = (
    "COMPLETE",
    "PARTIALLY_COMPLETE",
    "INCOMPLETE",
    "CONFLICTING",
)
PROPOSAL_STATUSES = ("DRAFT", "CONFIRMED", "REJECTED", "SUPERSEDED")
PROPOSAL_CREATED_BY_TYPES = ("LLM", "USER", "SYSTEM")
TASK_ITERATION_PHASES = ("ANALYZE", "EXECUTE", "REPAIR")
TASK_ITERATION_RESULTS = ("PROGRESS", "NO_PROGRESS", "ERROR")


def upgrade() -> None:
    op.create_table(
        "change_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("requester_id", sa.String(length=128), nullable=True),
        sa.Column("original_request", sa.Text(), nullable=False),
        sa.Column("base_revision", sa.String(length=64), nullable=True),
        sa.Column("base_workspace_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("active_proposal_id", sa.String(length=36), nullable=True),
        sa.Column("active_policy_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_lock_id", sa.String(length=36), nullable=True),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False),
        sa.Column("stagnation_count", sa.Integer(), nullable=False),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN {_quoted_values(TASK_STATUSES)}",
            name="ck_change_tasks_status_values",
        ),
        sa.CheckConstraint(
            "iteration_count >= 0",
            name="ck_change_tasks_iteration_count_non_negative",
        ),
        sa.CheckConstraint(
            "repair_count >= 0",
            name="ck_change_tasks_repair_count_non_negative",
        ),
        sa.CheckConstraint(
            "stagnation_count >= 0",
            name="ck_change_tasks_stagnation_count_non_negative",
        ),
        sa.CheckConstraint("version >= 1", name="ck_change_tasks_version_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_change_tasks_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_change_tasks"),
    )
    op.create_index("ix_change_tasks_project_id", "change_tasks", ["project_id"], unique=False)
    op.create_index("ix_change_tasks_status", "change_tasks", ["status"], unique=False)
    op.create_index("ix_change_tasks_created_at", "change_tasks", ["created_at"], unique=False)

    op.create_table(
        "change_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("current_problem", sa.Text(), nullable=True),
        sa.Column("expected_behavior", sa.Text(), nullable=False),
        sa.Column("initial_scope_json", sa.Text(), nullable=False),
        sa.Column("excluded_scope_json", sa.Text(), nullable=True),
        sa.Column("constraints_json", sa.Text(), nullable=True),
        sa.Column("assumptions_json", sa.Text(), nullable=True),
        sa.Column("risks_json", sa.Text(), nullable=True),
        sa.Column("acceptance_criteria_json", sa.Text(), nullable=False),
        sa.Column("validation_plan_json", sa.Text(), nullable=True),
        sa.Column("completeness", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_type", sa.String(length=16), nullable=False),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_change_proposals_version_positive"),
        sa.CheckConstraint(
            f"completeness IN {_quoted_values(PROPOSAL_COMPLETENESS_VALUES)}",
            name="ck_change_proposals_completeness_values",
        ),
        sa.CheckConstraint(
            f"status IN {_quoted_values(PROPOSAL_STATUSES)}",
            name="ck_change_proposals_status_values",
        ),
        sa.CheckConstraint(
            f"created_by_type IN {_quoted_values(PROPOSAL_CREATED_BY_TYPES)}",
            name="ck_change_proposals_created_by_type_values",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["change_proposals.id"],
            name="fk_change_proposals_supersedes_id_change_proposals",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_change_proposals_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_change_proposals"),
    )
    op.create_index("ix_change_proposals_task_id", "change_proposals", ["task_id"], unique=False)
    op.create_index(
        "ix_change_proposals_task_id_version",
        "change_proposals",
        ["task_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_change_proposals_supersedes_id",
        "change_proposals",
        ["supersedes_id"],
        unique=False,
    )

    op.create_table(
        "task_iterations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("context_token_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("progress_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "iteration_number >= 1",
            name="ck_task_iterations_iteration_number_positive",
        ),
        sa.CheckConstraint(
            f"phase IN {_quoted_values(TASK_ITERATION_PHASES)}",
            name="ck_task_iterations_phase_values",
        ),
        sa.CheckConstraint(
            "context_token_count IS NULL OR context_token_count >= 0",
            name="ck_task_iterations_context_token_count_non_negative",
        ),
        sa.CheckConstraint(
            f"result IS NULL OR result IN {_quoted_values(TASK_ITERATION_RESULTS)}",
            name="ck_task_iterations_result_values",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_task_iterations_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_iterations"),
    )
    op.create_index("ix_task_iterations_task_id", "task_iterations", ["task_id"], unique=False)
    op.create_index(
        "ix_task_iterations_task_id_iteration_number",
        "task_iterations",
        ["task_id", "iteration_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_task_iterations_task_id_iteration_number", table_name="task_iterations")
    op.drop_index("ix_task_iterations_task_id", table_name="task_iterations")
    op.drop_table("task_iterations")
    op.drop_index("ix_change_proposals_supersedes_id", table_name="change_proposals")
    op.drop_index("ix_change_proposals_task_id_version", table_name="change_proposals")
    op.drop_index("ix_change_proposals_task_id", table_name="change_proposals")
    op.drop_table("change_proposals")
    op.drop_index("ix_change_tasks_created_at", table_name="change_tasks")
    op.drop_index("ix_change_tasks_status", table_name="change_tasks")
    op.drop_index("ix_change_tasks_project_id", table_name="change_tasks")
    op.drop_table("change_tasks")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
