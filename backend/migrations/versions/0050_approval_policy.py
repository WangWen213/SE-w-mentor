"""Approval and execution policy persistence.

Revision ID: 0050_approval_policy
Revises: 0040_governance
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_approval_policy"
down_revision = "0040_governance"
branch_labels = None
depends_on = None

APPROVAL_REQUEST_STATUSES = ("PENDING", "APPROVED", "REJECTED", "EXPIRED", "SUPERSEDED")
APPROVAL_DECISION_OUTCOMES = ("APPROVED", "REJECTED", "REVOKED")
EXECUTION_POLICY_STATUSES = ("ACTIVE", "EXPIRED", "SUPERSEDED", "REVOKED")


def upgrade() -> None:
    op.create_index(
        "ix_governance_decisions_id_proposal_revision",
        "governance_decisions",
        ["id", "proposal_hash", "revision"],
        unique=True,
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("governance_decision_id", sa.String(length=36), nullable=False),
        sa.Column("decision_revision", sa.String(length=64), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_scope_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        sa.CheckConstraint(
            "length(trim(decision_revision)) > 0",
            name="decision_revision_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(requested_scope_json)) > 0",
            name="requested_scope_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.CheckConstraint(
            f"status IN {_quoted_values(APPROVAL_REQUEST_STATUSES)}",
            name="status_values",
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["agent_actions.id"],
            name="fk_approval_requests_action_id_agent_actions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["governance_decision_id", "proposal_hash", "decision_revision"],
            [
                "governance_decisions.id",
                "governance_decisions.proposal_hash",
                "governance_decisions.revision",
            ],
            name="fk_approval_requests_decision_proposal_revision_governance_decisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_approval_requests_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_requests"),
        sa.UniqueConstraint("id", "proposal_hash", name="uq_approval_requests_id_proposal_hash"),
    )
    op.create_index("ix_approval_requests_task_id", "approval_requests", ["task_id"])
    op.create_index("ix_approval_requests_action_id", "approval_requests", ["action_id"])
    op.create_index(
        "ix_approval_requests_governance_decision_id",
        "approval_requests",
        ["governance_decision_id"],
    )
    op.create_index(
        "ix_approval_requests_task_id_status",
        "approval_requests",
        ["task_id", "status"],
    )
    op.create_index("ix_approval_requests_proposal_hash", "approval_requests", ["proposal_hash"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("approver_id", sa.String(length=128), nullable=False),
        sa.Column("approved_scope_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("decision_sequence >= 1", name="decision_sequence_positive"),
        sa.CheckConstraint(
            f"outcome IN {_quoted_values(APPROVAL_DECISION_OUTCOMES)}",
            name="outcome_values",
        ),
        sa.CheckConstraint("length(trim(approver_id)) > 0", name="approver_id_non_empty"),
        sa.CheckConstraint(
            "length(trim(approved_scope_json)) > 0",
            name="approved_scope_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["approval_requests.id"],
            name="fk_approval_decisions_approval_request_id_approval_requests",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_decisions"),
    )
    op.create_index(
        "ix_approval_decisions_approval_request_id",
        "approval_decisions",
        ["approval_request_id"],
    )
    op.create_index(
        "ix_approval_decisions_request_sequence",
        "approval_decisions",
        ["approval_request_id", "decision_sequence"],
        unique=True,
    )

    op.create_table(
        "execution_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("governance_decision_id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("executable", sa.Boolean(), nullable=False),
        sa.Column("read_paths_json", sa.Text(), nullable=False),
        sa.Column("write_paths_json", sa.Text(), nullable=False),
        sa.Column("protected_paths_json", sa.Text(), nullable=False),
        sa.Column("commands_json", sa.Text(), nullable=False),
        sa.Column("network_json", sa.Text(), nullable=False),
        sa.Column("resource_limits_json", sa.Text(), nullable=False),
        sa.Column("invalidation_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        sa.CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        sa.CheckConstraint(
            f"status IN {_quoted_values(EXECUTION_POLICY_STATUSES)}",
            name="status_values",
        ),
        sa.CheckConstraint("length(trim(read_paths_json)) > 0", name="read_paths_non_empty"),
        sa.CheckConstraint("length(trim(write_paths_json)) > 0", name="write_paths_non_empty"),
        sa.CheckConstraint(
            "length(trim(protected_paths_json)) > 0",
            name="protected_paths_non_empty",
        ),
        sa.CheckConstraint("length(trim(commands_json)) > 0", name="commands_non_empty"),
        sa.CheckConstraint("length(trim(network_json)) > 0", name="network_non_empty"),
        sa.CheckConstraint(
            "length(trim(resource_limits_json)) > 0",
            name="resource_limits_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(invalidation_json)) > 0",
            name="invalidation_non_empty",
        ),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["agent_actions.id"],
            name="fk_execution_policies_action_id_agent_actions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id", "proposal_hash"],
            ["approval_requests.id", "approval_requests.proposal_hash"],
            name="fk_execution_policies_approval_proposal_approval_requests",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["governance_decision_id"],
            ["governance_decisions.id"],
            name="fk_execution_policies_governance_decision_id_governance_decisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_execution_policies_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_policies"),
    )
    op.create_index("ix_execution_policies_task_id", "execution_policies", ["task_id"])
    op.create_index("ix_execution_policies_action_id", "execution_policies", ["action_id"])
    op.create_index(
        "ix_execution_policies_governance_decision_id",
        "execution_policies",
        ["governance_decision_id"],
    )
    op.create_index(
        "ix_execution_policies_approval_request_id",
        "execution_policies",
        ["approval_request_id"],
    )
    op.create_index(
        "ix_execution_policies_task_id_status",
        "execution_policies",
        ["task_id", "status"],
    )
    op.create_index(
        "ix_execution_policies_proposal_hash_revision",
        "execution_policies",
        ["proposal_hash", "revision"],
    )
    op.execute(_no_active_block_trigger("insert"))
    op.execute(_no_active_block_trigger("update"))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_execution_policies_no_active_block_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_execution_policies_no_active_block_update")
    op.drop_index("ix_execution_policies_proposal_hash_revision", table_name="execution_policies")
    op.drop_index("ix_execution_policies_task_id_status", table_name="execution_policies")
    op.drop_index("ix_execution_policies_approval_request_id", table_name="execution_policies")
    op.drop_index("ix_execution_policies_governance_decision_id", table_name="execution_policies")
    op.drop_index("ix_execution_policies_action_id", table_name="execution_policies")
    op.drop_index("ix_execution_policies_task_id", table_name="execution_policies")
    op.drop_table("execution_policies")
    op.drop_index("ix_approval_decisions_request_sequence", table_name="approval_decisions")
    op.drop_index("ix_approval_decisions_approval_request_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")
    op.drop_index("ix_approval_requests_proposal_hash", table_name="approval_requests")
    op.drop_index("ix_approval_requests_task_id_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_governance_decision_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_action_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_task_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(
        "ix_governance_decisions_id_proposal_revision",
        table_name="governance_decisions",
    )


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _no_active_block_trigger(operation: str) -> str:
    return f"""
    CREATE TRIGGER trg_execution_policies_no_active_block_{operation}
    BEFORE {operation.upper()} ON execution_policies
    WHEN NEW.status = 'ACTIVE' AND NEW.executable = 1
         AND EXISTS (
             SELECT 1 FROM governance_decisions
             WHERE id = NEW.governance_decision_id AND decision = 'BLOCK'
         )
    BEGIN
        SELECT RAISE(ABORT, 'BLOCK governance decision cannot have ACTIVE executable policy');
    END
    """
