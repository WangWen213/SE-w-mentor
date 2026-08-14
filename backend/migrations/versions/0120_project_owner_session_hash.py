"""Project owner session hash for ONLINE_SAFE isolation.

Revision ID: 0120_project_owner_session_hash
Revises: 0110_task_evaluations
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120_project_owner_session_hash"
down_revision = "0110_task_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("owner_session_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_projects_owner_session_hash", "projects", ["owner_session_hash"])


def downgrade() -> None:
    op.drop_index("ix_projects_owner_session_hash", table_name="projects")
    op.drop_column("projects", "owner_session_hash")
