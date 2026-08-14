from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.project import Project, normalize_project_root_path


def find_project_by_root(session: Session, root_path: Path) -> Project | None:
    normalized = normalize_project_root_path(root_path.resolve())
    return session.scalar(select(Project).where(Project.normalized_root_path == normalized))


def add_project(
    session: Session,
    root_path: Path,
    *,
    owner_session_hash: str | None = None,
) -> Project:
    project = Project(
        root_path=str(root_path.resolve()),
        owner_session_hash=owner_session_hash,
    )
    session.add(project)
    session.flush()
    return project
