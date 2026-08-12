from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from se_mentor.db.base import Base
from se_mentor.models.task import _in_values


class WorkbenchMessageRole(StrEnum):
    MENTOR = "MENTOR"
    SYSTEM = "SYSTEM"
    USER = "USER"


class WorkbenchMessageKind(StrEnum):
    ERROR = "ERROR"
    PROPOSAL = "PROPOSAL"
    TEXT = "TEXT"


class WorkbenchMessageStatus(StrEnum):
    DONE = "DONE"
    ERROR = "ERROR"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkbenchMessage(Base):
    __tablename__ = "workbench_messages"
    __table_args__ = (
        CheckConstraint(
            f"role IN {_in_values(WorkbenchMessageRole)}",
            name="role_values",
        ),
        CheckConstraint(
            f"kind IN {_in_values(WorkbenchMessageKind)}",
            name="kind_values",
        ),
        CheckConstraint(
            f"status IN {_in_values(WorkbenchMessageStatus)}",
            name="status_values",
        ),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        Index("ix_workbench_messages_task_id_sequence", "task_id", "sequence", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("change_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
