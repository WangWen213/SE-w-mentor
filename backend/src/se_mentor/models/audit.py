from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    DDL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.contracts.enums import EventType
from se_mentor.db.base import Base
from se_mentor.models.task import ChangeTask


class AuditActorType(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    AGENT = "AGENT"
    TOOL = "TOOL"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(f"actor_type IN {_in_values(AuditActorType)}", name="actor_type_values"),
        CheckConstraint(f"event_type IN {_in_values(EventType)}", name="event_type_values"),
        CheckConstraint("length(trim(correlation_id)) > 0", name="correlation_id_non_empty"),
        CheckConstraint("length(trim(actor_id)) > 0", name="actor_id_non_empty"),
        CheckConstraint("length(trim(payload_summary)) > 0", name="payload_summary_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_audit_events_task_id_created_at", "task_id", "created_at"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    task: Mapped[ChangeTask | None] = relationship()


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(f"severity IN {_in_values(AlertSeverity)}", name="severity_values"),
        CheckConstraint(f"status IN {_in_values(AlertStatus)}", name="status_values"),
        CheckConstraint("task_id IS NOT NULL OR system_scope = 1", name="task_or_system_scope"),
        CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_alert_events_task_id_status", "task_id", "status"),
        Index("ix_alert_events_severity_status", "severity", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    system_scope: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[ChangeTask | None] = relationship()


_AUDIT_NO_UPDATE = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update
    BEFORE UPDATE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events are append-only');
    END
    """
).execute_if(dialect="sqlite")

_AUDIT_NO_DELETE = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete
    BEFORE DELETE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events are append-only');
    END
    """
).execute_if(dialect="sqlite")

event.listen(AuditEvent.__table__, "after_create", _AUDIT_NO_UPDATE)
event.listen(AuditEvent.__table__, "after_create", _AUDIT_NO_DELETE)
