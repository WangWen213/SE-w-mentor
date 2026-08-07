"""Project domain persistence.

Revision ID: 0010_project_domain
Revises: 0001_initial_baseline
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_project_domain"
down_revision = "0001_initial_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("normalized_root_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("normalized_root_path", name="uq_projects_normalized_root_path"),
    )
    op.create_table(
        "project_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_scope", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_configs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_configs"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_configs_project_id_version"),
    )
    op.create_index(
        "ix_project_configs_project_id",
        "project_configs",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "credential_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("keyring_reference", sa.String(length=512), nullable=False),
        sa.Column("configuration_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_credential_profiles_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_credential_profiles"),
    )
    op.create_index(
        "ix_credential_profiles_project_id",
        "credential_profiles",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_credential_profiles_project_id", table_name="credential_profiles")
    op.drop_table("credential_profiles")
    op.drop_index("ix_project_configs_project_id", table_name="project_configs")
    op.drop_table("project_configs")
    op.drop_table("projects")
