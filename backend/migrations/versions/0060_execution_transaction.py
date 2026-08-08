"""Execution, transaction, backup, file change, and lock persistence.

Revision ID: 0060_execution_transaction
Revises: 0050_approval_policy
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060_execution_transaction"
down_revision = "0050_approval_policy"
branch_labels = None
depends_on = None

LOCK_MODES = ("READ", "WRITE")
LOCK_STATUSES = ("ACTIVE", "RELEASED", "EXPIRED")
TRANSACTION_STATES = ("PREPARED", "APPLYING", "COMMITTED", "ROLLED_BACK", "CONFLICT")
TOOL_STATUSES = ("RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED")
FILE_CHANGE_TYPES = ("CREATE", "MODIFY", "DELETE")


def upgrade() -> None:
    op.create_table(
        "workspace_locks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("lock_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"lock_mode IN {_quoted_values(LOCK_MODES)}", name="lock_mode_values"),
        sa.CheckConstraint(f"status IN {_quoted_values(LOCK_STATUSES)}", name="status_values"),
        sa.CheckConstraint("length(trim(owner)) > 0", name="owner_non_empty"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="reason_non_empty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_locks_project_id", "workspace_locks", ["project_id"])
    op.create_index("ix_workspace_locks_task_id", "workspace_locks", ["task_id"])
    op.create_index(
        "ix_workspace_locks_one_active_write_per_project",
        "workspace_locks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("lock_mode = 'WRITE' AND status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_workspace_locks_project_id_status",
        "workspace_locks",
        ["project_id", "status"],
    )

    op.create_table(
        "task_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_lock_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("manifest_artifact_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"state IN {_quoted_values(TRANSACTION_STATES)}", name="state_values"),
        sa.CheckConstraint(
            "state != 'COMMITTED' OR length(trim(manifest_artifact_ref)) > 0",
            name="committed_manifest_required",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_lock_id"], ["workspace_locks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_transactions_task_id", "task_transactions", ["task_id"])
    op.create_index("ix_task_transactions_project_id", "task_transactions", ["project_id"])
    op.create_index(
        "ix_task_transactions_workspace_lock_id",
        "task_transactions",
        ["workspace_lock_id"],
    )
    op.create_index(
        "ix_task_transactions_task_id_state",
        "task_transactions",
        ["task_id", "state"],
    )
    op.execute(_committed_lock_trigger("insert"))
    op.execute(_committed_lock_trigger("update"))

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("command_summary", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN {_quoted_values(TOOL_STATUSES)}", name="status_values"),
        sa.CheckConstraint("exit_code IS NULL OR exit_code >= 0", name="exit_code_non_negative"),
        sa.CheckConstraint("length(trim(tool_name)) > 0", name="tool_name_non_empty"),
        sa.CheckConstraint(
            "length(trim(command_summary)) > 0",
            name="command_summary_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["action_id"], ["agent_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["task_transactions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_executions_task_id", "tool_executions", ["task_id"])
    op.create_index("ix_tool_executions_action_id", "tool_executions", ["action_id"])
    op.create_index("ix_tool_executions_transaction_id", "tool_executions", ["transaction_id"])
    op.create_index(
        "ix_tool_executions_task_id_status",
        "tool_executions",
        ["task_id", "status"],
    )

    op.create_table(
        "backup_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_hash", sa.String(length=64), nullable=False),
        sa.Column("backup_artifact_ref", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=128), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(original_hash) = 64", name="original_hash_length"),
        sa.CheckConstraint(
            "length(trim(backup_artifact_ref)) > 0",
            name="backup_artifact_ref_non_empty",
        ),
        sa.CheckConstraint("length(trim(file_type)) > 0", name="file_type_non_empty"),
        sa.CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_entries_task_id", "backup_entries", ["task_id"])
    op.create_index("ix_backup_entries_project_id", "backup_entries", ["project_id"])
    op.create_index(
        "ix_backup_entries_task_id_relative_path",
        "backup_entries",
        ["task_id", "relative_path"],
    )

    op.create_table(
        "file_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tool_execution_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("backup_entry_id", sa.String(length=36), nullable=True),
        sa.Column("change_type", sa.String(length=16), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"change_type IN {_quoted_values(FILE_CHANGE_TYPES)}",
            name="change_type_values",
        ),
        sa.CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        sa.CheckConstraint(
            "before_hash IS NULL OR length(before_hash) = 64", name="before_hash_length"
        ),
        sa.CheckConstraint(
            "after_hash IS NULL OR length(after_hash) = 64", name="after_hash_length"
        ),
        sa.ForeignKeyConstraint(["action_id"], ["agent_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["backup_entry_id"], ["backup_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["change_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_execution_id"], ["tool_executions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_changes_task_id", "file_changes", ["task_id"])
    op.create_index("ix_file_changes_tool_execution_id", "file_changes", ["tool_execution_id"])
    op.create_index("ix_file_changes_action_id", "file_changes", ["action_id"])


def downgrade() -> None:
    op.drop_index("ix_file_changes_action_id", table_name="file_changes")
    op.drop_index("ix_file_changes_tool_execution_id", table_name="file_changes")
    op.drop_index("ix_file_changes_task_id", table_name="file_changes")
    op.drop_table("file_changes")
    op.drop_index("ix_backup_entries_task_id_relative_path", table_name="backup_entries")
    op.drop_index("ix_backup_entries_project_id", table_name="backup_entries")
    op.drop_index("ix_backup_entries_task_id", table_name="backup_entries")
    op.drop_table("backup_entries")
    op.drop_index("ix_tool_executions_task_id_status", table_name="tool_executions")
    op.drop_index("ix_tool_executions_transaction_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_action_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_task_id", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.execute("DROP TRIGGER IF EXISTS trg_task_transactions_committed_write_lock_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_task_transactions_committed_write_lock_update")
    op.drop_index("ix_task_transactions_task_id_state", table_name="task_transactions")
    op.drop_index("ix_task_transactions_workspace_lock_id", table_name="task_transactions")
    op.drop_index("ix_task_transactions_project_id", table_name="task_transactions")
    op.drop_index("ix_task_transactions_task_id", table_name="task_transactions")
    op.drop_table("task_transactions")
    op.drop_index("ix_workspace_locks_project_id_status", table_name="workspace_locks")
    op.drop_index("ix_workspace_locks_one_active_write_per_project", table_name="workspace_locks")
    op.drop_index("ix_workspace_locks_task_id", table_name="workspace_locks")
    op.drop_index("ix_workspace_locks_project_id", table_name="workspace_locks")
    op.drop_table("workspace_locks")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _committed_lock_trigger(operation: str) -> str:
    return f"""
    CREATE TRIGGER trg_task_transactions_committed_write_lock_{operation}
    BEFORE {operation.upper()} ON task_transactions
    WHEN NEW.state = 'COMMITTED'
         AND NOT EXISTS (
             SELECT 1 FROM workspace_locks
             WHERE id = NEW.workspace_lock_id
               AND project_id = NEW.project_id
               AND lock_mode = 'WRITE'
               AND status = 'ACTIVE'
         )
    BEGIN
        SELECT RAISE(ABORT, 'COMMITTED transaction requires active WRITE lock');
    END
    """
