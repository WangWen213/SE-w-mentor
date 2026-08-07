"""LLM and action domain persistence.

Revision ID: 0030_llm_action
Revises: 0020_task_domain
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_llm_action"
down_revision = "0020_task_domain"
branch_labels = None
depends_on = None

LLM_CALL_STATUSES = ("SUCCESS", "TIMEOUT", "ERROR", "INVALID_OUTPUT")
PARSE_STATUSES = ("VALID", "INVALID")
ACTION_TYPES = (
    "READ_FILE",
    "SEARCH_CODE",
    "APPLY_PATCH",
    "CREATE_FILE",
    "DELETE_FILE",
    "RUN_COMMAND",
)
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
AGENT_ACTION_STATUSES = (
    "PARSED",
    "GOVERNING",
    "WAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "BLOCKED",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("iteration_id", sa.String(length=36), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("request_summary", sa.String(length=2048), nullable=True),
        sa.Column("response_summary", sa.String(length=2048), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("compression_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN {_quoted_values(LLM_CALL_STATUSES)}",
            name="status_values",
        ),
        sa.CheckConstraint(
            f"parse_status IN {_quoted_values(PARSE_STATUSES)}",
            name="parse_status_values",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name="input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name="output_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "compression_count >= 0",
            name="compression_count_non_negative",
        ),
        sa.CheckConstraint("retry_count >= 0", name="retry_count_non_negative"),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="latency_ms_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["iteration_id"],
            ["task_iterations.id"],
            name="fk_llm_calls_iteration_id_task_iterations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_calls"),
    )
    op.create_index("ix_llm_calls_iteration_id", "llm_calls", ["iteration_id"], unique=False)
    op.create_index("ix_llm_calls_provider_name", "llm_calls", ["provider_name"], unique=False)
    op.create_index("ix_llm_calls_model_name", "llm_calls", ["model_name"], unique=False)
    op.create_index("ix_llm_calls_parse_status", "llm_calls", ["parse_status"], unique=False)

    op.create_table(
        "agent_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("iteration_id", sa.String(length=36), nullable=False),
        sa.Column("llm_call_id", sa.String(length=36), nullable=True),
        sa.Column("action_sequence", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("parameters_summary", sa.String(length=2048), nullable=False),
        sa.Column("parameters_artifact_ref", sa.String(length=512), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_sequence >= 1",
            name="action_sequence_positive",
        ),
        sa.CheckConstraint(
            f"action_type IN {_quoted_values(ACTION_TYPES)}",
            name="action_type_values",
        ),
        sa.CheckConstraint(
            f"parse_status IN {_quoted_values(PARSE_STATUSES)}",
            name="parse_status_values",
        ),
        sa.CheckConstraint(
            f"risk_level IS NULL OR risk_level IN {_quoted_values(RISK_LEVELS)}",
            name="risk_level_values",
        ),
        sa.CheckConstraint(
            f"status IN {_quoted_values(AGENT_ACTION_STATUSES)}",
            name="status_values",
        ),
        sa.ForeignKeyConstraint(
            ["iteration_id"],
            ["task_iterations.id"],
            name="fk_agent_actions_iteration_id_task_iterations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["llm_calls.id"],
            name="fk_agent_actions_llm_call_id_llm_calls",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["change_tasks.id"],
            name="fk_agent_actions_task_id_change_tasks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_actions"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_actions_idempotency_key"),
    )
    op.create_index(
        "ix_agent_actions_iteration_id",
        "agent_actions",
        ["iteration_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_actions_iteration_id_action_sequence",
        "agent_actions",
        ["iteration_id", "action_sequence"],
        unique=True,
    )
    op.create_index(
        "ix_agent_actions_action_type",
        "agent_actions",
        ["action_type"],
        unique=False,
    )
    op.create_index("ix_agent_actions_status", "agent_actions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_actions_status", table_name="agent_actions")
    op.drop_index("ix_agent_actions_action_type", table_name="agent_actions")
    op.drop_index("ix_agent_actions_iteration_id_action_sequence", table_name="agent_actions")
    op.drop_index("ix_agent_actions_iteration_id", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_index("ix_llm_calls_parse_status", table_name="llm_calls")
    op.drop_index("ix_llm_calls_model_name", table_name="llm_calls")
    op.drop_index("ix_llm_calls_provider_name", table_name="llm_calls")
    op.drop_index("ix_llm_calls_iteration_id", table_name="llm_calls")
    op.drop_table("llm_calls")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
