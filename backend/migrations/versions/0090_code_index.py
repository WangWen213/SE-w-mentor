"""Code index persistence.

Revision ID: 0090_code_index
Revises: 0080_knowledge
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0090_code_index"
down_revision = "0080_knowledge"
branch_labels = None
depends_on = None

INDEX_STATUSES = ("BUILDING", "READY", "STALE", "FAILED")
SYMBOL_KINDS = ("MODULE", "CLASS", "FUNCTION", "METHOD", "API", "DTO", "TABLE", "TEST")
RELATION_TYPES = ("IMPORTS", "CALLS", "TESTS", "SERIALIZES", "READS_TABLE", "WRITES_TABLE")


def upgrade() -> None:
    op.create_table(
        "code_indexes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("index_generation", sa.Integer(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN {_quoted_values(INDEX_STATUSES)}", name="status_values"),
        sa.CheckConstraint("index_generation >= 1", name="index_generation_positive"),
        sa.CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        sa.CheckConstraint("length(trim(language)) > 0", name="language_non_empty"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "revision",
            "language",
            name="uq_code_indexes_project_revision_language",
        ),
    )
    op.create_index("ix_code_indexes_project_id", "code_indexes", ["project_id"])
    op.create_index("ix_code_indexes_project_status", "code_indexes", ["project_id", "status"])

    op.create_table(
        "code_symbols",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_index_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("symbol_key", sa.String(length=512), nullable=False),
        sa.Column("qualified_name", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("signature_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN {_quoted_values(SYMBOL_KINDS)}", name="kind_values"),
        sa.CheckConstraint("length(trim(symbol_key)) > 0", name="symbol_key_non_empty"),
        sa.CheckConstraint("length(trim(qualified_name)) > 0", name="qualified_name_non_empty"),
        sa.CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        sa.ForeignKeyConstraint(["code_index_id"], ["code_indexes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", "revision", name="uq_code_symbols_id_project_revision"
        ),
        sa.UniqueConstraint("code_index_id", "symbol_key", name="uq_code_symbols_index_symbol_key"),
    )
    op.create_index("ix_code_symbols_code_index_id", "code_symbols", ["code_index_id"])
    op.create_index("ix_code_symbols_project_id", "code_symbols", ["project_id"])
    op.create_index(
        "ix_code_symbols_project_revision_kind",
        "code_symbols",
        ["project_id", "revision", "kind"],
    )

    op.create_table(
        "code_symbol_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_symbol_id", sa.String(length=36), nullable=False),
        sa.Column("source_project_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision", sa.String(length=64), nullable=False),
        sa.Column("target_symbol_id", sa.String(length=36), nullable=False),
        sa.Column("target_project_id", sa.String(length=36), nullable=False),
        sa.Column("target_revision", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"relation_type IN {_quoted_values(RELATION_TYPES)}",
            name="relation_type_values",
        ),
        sa.CheckConstraint("source_project_id = target_project_id", name="same_project"),
        sa.CheckConstraint("source_revision = target_revision", name="same_revision"),
        sa.CheckConstraint("source_symbol_id != target_symbol_id", name="no_self_relation"),
        sa.CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        sa.ForeignKeyConstraint(
            ["source_symbol_id", "source_project_id", "source_revision"],
            ["code_symbols.id", "code_symbols.project_id", "code_symbols.revision"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_symbol_id", "target_project_id", "target_revision"],
            ["code_symbols.id", "code_symbols.project_id", "code_symbols.revision"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_symbol_id",
            "target_symbol_id",
            "relation_type",
            name="uq_code_symbol_relations_source_target_type",
        ),
    )
    op.create_index(
        "ix_code_symbol_relations_source", "code_symbol_relations", ["source_symbol_id"]
    )
    op.create_index(
        "ix_code_symbol_relations_target", "code_symbol_relations", ["target_symbol_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_code_symbol_relations_target", table_name="code_symbol_relations")
    op.drop_index("ix_code_symbol_relations_source", table_name="code_symbol_relations")
    op.drop_table("code_symbol_relations")
    op.drop_index("ix_code_symbols_project_revision_kind", table_name="code_symbols")
    op.drop_index("ix_code_symbols_project_id", table_name="code_symbols")
    op.drop_index("ix_code_symbols_code_index_id", table_name="code_symbols")
    op.drop_table("code_symbols")
    op.drop_index("ix_code_indexes_project_status", table_name="code_indexes")
    op.drop_index("ix_code_indexes_project_id", table_name="code_indexes")
    op.drop_table("code_indexes")


def _quoted_values(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
