from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from se_mentor.db.base import Base

FORBIDDEN_CREDENTIAL_FIELDS = {
    "secret",
    "api_key",
    "token",
    "password",
    "credential_value",
}


def normalize_project_root_path(root_path: str | Path, *, base_path: Path | None = None) -> str:
    path = Path(root_path).expanduser()
    if not path.is_absolute():
        path = (base_path or Path.cwd()) / path
    normalized = os.path.normpath(str(path))
    return os.path.normcase(normalized) if os.name == "nt" else normalized


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("normalized_root_path", name="uq_projects_normalized_root_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_root_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    configs: Mapped[list[ProjectConfig]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    credential_profiles: Mapped[list[CredentialProfile]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("root_path")
    def _set_normalized_root_path(self, _key: str, value: str) -> str:
        self.normalized_root_path = normalize_project_root_path(value)
        return value


class ProjectConfig(TimestampMixin, Base):
    __tablename__ = "project_configs"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_configs_project_id_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped[Project] = relationship(back_populates="configs")


class CredentialProfile(TimestampMixin, Base):
    __tablename__ = "credential_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    keyring_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    configuration_status: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped[Project] = relationship(back_populates="credential_profiles")

    def __init__(self, **kwargs: Any) -> None:
        forbidden = FORBIDDEN_CREDENTIAL_FIELDS.intersection(kwargs)
        if forbidden:
            raise TypeError(f"credential plaintext fields are not persisted: {sorted(forbidden)}")
        super().__init__(**kwargs)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in FORBIDDEN_CREDENTIAL_FIELDS:
            raise AttributeError(f"credential plaintext field is not persisted: {key}")
        super().__setattr__(key, value)
