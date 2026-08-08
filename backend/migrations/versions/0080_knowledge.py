"""Engineering knowledge persistence.

Revision ID: 0080_knowledge
Revises: 0070_validation_feedback
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0080_knowledge"
down_revision = "0070_validation_feedback"
branch_labels = None
depends_on = None

KNOWLEDGE_STATUSES = (
    "CANDIDATE",
    "VERIFIED",
    "REVIEWED",
    "FAILED_EXPERIENCE",
    "CONFLICTING",
    "DEPRECATED",
    "STALE",
)
KNOWLEDGE_TYPES = ("PATTERN", "DECISION", "CONSTRAINT", "FAILURE")
SOURCE_TYPES = ("LLM_SUMMARY", "TEST", "USER_REVIEW", "COMMITTED_DIFF")
RELATION_TYPES = ("SUPERSEDES", "CONFLICTS_WITH", "SUPPORTS")


def upgrade() -> None:
    op.create_table(
        "engineering_knowledge",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_key", sa.String(length=256), nullable=False),
        sa.Column("knowledge_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(length=2048), nullable=False),
        sa.Column("verified_evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"knowledge_type IN {_quoted_values(KNOWLEDGE_TYPES)}",
            name="knowledge_type_values",
        ),
        sa.CheckConstraint(f"status IN {_quoted_values(KNOWLEDGE_STATUSES)}", name="status_values"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("length(trim(knowledge_key)) > 0", name="knowledge_key_non_empty"),
        sa.CheckConstraint("length(trim(scope_json)) > 0", name="scope_non_empty"),
        sa.CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        sa.CheckConstraint(
            "status != 'VERIFIED' OR "
            "(verified_evidence_json IS NOT NULL AND length(trim(verified_evidence_json)) > 0)",
            name="verified_requires_evidence",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "knowledge_key",
            "version",
            name="uq_engineering_knowledge_project_key_version",
        ),
    )
    op.create_index("ix_engineering_knowledge_project_id", "engineering_knowledge", ["project_id"])
    op.create_index(
        "ix_engineering_knowledge_project_type_status",
        "engineering_knowledge",
        ["project_id", "knowledge_type", "status"],
    )

    op.create_table(
        "knowledge_signatures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_id", sa.String(length=36), nullable=False),
        sa.Column("signature_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(signature_hash) = 64", name="signature_hash_length"),
        sa.ForeignKeyConstraint(
            ["knowledge_id"], ["engineering_knowledge.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_signatures_knowledge_id", "knowledge_signatures", ["knowledge_id"]
    )
    op.create_index(
        "ix_knowledge_signatures_signature_hash",
        "knowledge_signatures",
        ["signature_hash"],
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"source_type IN {_quoted_values(SOURCE_TYPES)}", name="source_type_values"
        ),
        sa.CheckConstraint("length(trim(source_ref)) > 0", name="source_ref_non_empty"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["knowledge_id"], ["engineering_knowledge.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_sources_knowledge_id", "knowledge_sources", ["knowledge_id"])
    op.create_index(
        "ix_knowledge_sources_knowledge_type",
        "knowledge_sources",
        ["knowledge_id", "source_type"],
    )

    op.create_table(
        "knowledge_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_knowledge_id", sa.String(length=36), nullable=False),
        sa.Column("target_knowledge_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"relation_type IN {_quoted_values(RELATION_TYPES)}",
            name="relation_type_values",
        ),
        sa.CheckConstraint("source_knowledge_id != target_knowledge_id", name="no_self_relation"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_knowledge_id"], ["engineering_knowledge.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_knowledge_id"], ["engineering_knowledge.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_knowledge_id",
            "target_knowledge_id",
            "relation_type",
            name="uq_knowledge_relations_source_target_type",
        ),
    )
    op.create_index("ix_knowledge_relations_project_id", "knowledge_relations", ["project_id"])
    op.create_index(
        "ix_knowledge_relations_source_knowledge_id", "knowledge_relations", ["source_knowledge_id"]
    )
    op.create_index(
        "ix_knowledge_relations_target_knowledge_id", "knowledge_relations", ["target_knowledge_id"]
    )
    op.create_index(
        "ix_knowledge_relations_project_type",
        "knowledge_relations",
        ["project_id", "relation_type"],
    )
    op.execute(_knowledge_relation_project_trigger("insert"))
    op.execute(_knowledge_relation_project_trigger("update"))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_relations_project_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_relations_project_update")
    op.drop_index("ix_knowledge_relations_project_type", table_name="knowledge_relations")
    op.drop_index("ix_knowledge_relations_target_knowledge_id", table_name="knowledge_relations")
    op.drop_index("ix_knowledge_relations_source_knowledge_id", table_name="knowledge_relations")
    op.drop_index("ix_knowledge_relations_project_id", table_name="knowledge_relations")
    op.drop_table("knowledge_relations")
    op.drop_index("ix_knowledge_sources_knowledge_type", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_knowledge_id", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.drop_index("ix_knowledge_signatures_signature_hash", table_name="knowledge_signatures")
    op.drop_index("ix_knowledge_signatures_knowledge_id", table_name="knowledge_signatures")
    op.drop_table("knowledge_signatures")
    op.drop_index(
        "ix_engineering_knowledge_project_type_status", table_name="engineering_knowledge"
    )
    op.drop_index("ix_engineering_knowledge_project_id", table_name="engineering_knowledge")
    op.drop_table("engineering_knowledge")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _knowledge_relation_project_trigger(operation: str) -> str:
    return f"""
    CREATE TRIGGER trg_knowledge_relations_project_{operation}
    BEFORE {operation.upper()} ON knowledge_relations
    WHEN NOT EXISTS (
        SELECT 1
        FROM engineering_knowledge source
        JOIN engineering_knowledge target ON target.id = NEW.target_knowledge_id
        WHERE source.id = NEW.source_knowledge_id
          AND source.project_id = NEW.project_id
          AND target.project_id = NEW.project_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'knowledge relation cannot cross project');
    END
    """
