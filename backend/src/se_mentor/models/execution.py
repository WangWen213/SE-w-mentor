from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    DDL,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.llm import AgentAction
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask


class WorkspaceLockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"


class WorkspaceLockStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class TransactionState(StrEnum):
    PREPARED = "PREPARED"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    CONFLICT = "CONFLICT"


class ToolExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class FileChangeType(StrEnum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class WorkspaceLock(Base):
    __tablename__ = "workspace_locks"
    __table_args__ = (
        CheckConstraint(f"lock_mode IN {_in_values(WorkspaceLockMode)}", name="lock_mode_values"),
        CheckConstraint(f"status IN {_in_values(WorkspaceLockStatus)}", name="status_values"),
        CheckConstraint("length(trim(owner)) > 0", name="owner_non_empty"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_non_empty"),
        Index(
            "ix_workspace_locks_one_active_write_per_project",
            "project_id",
            unique=True,
            sqlite_where=text("lock_mode = 'WRITE' AND status = 'ACTIVE'"),
        ),
        Index("ix_workspace_locks_project_id_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lock_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship()
    task: Mapped[ChangeTask] = relationship()


class TaskTransaction(Base):
    __tablename__ = "task_transactions"
    __table_args__ = (
        CheckConstraint(f"state IN {_in_values(TransactionState)}", name="state_values"),
        CheckConstraint(
            "state != 'COMMITTED' OR length(trim(manifest_artifact_ref)) > 0",
            name="committed_manifest_required",
        ),
        Index("ix_task_transactions_task_id_state", "task_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workspace_lock_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspace_locks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    manifest_artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    task: Mapped[ChangeTask] = relationship()
    project: Mapped[Project] = relationship()
    workspace_lock: Mapped[WorkspaceLock | None] = relationship()


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(f"status IN {_in_values(ToolExecutionStatus)}", name="status_values"),
        CheckConstraint("exit_code IS NULL OR exit_code >= 0", name="exit_code_non_negative"),
        CheckConstraint("length(trim(tool_name)) > 0", name="tool_name_non_empty"),
        CheckConstraint("length(trim(command_summary)) > 0", name="command_summary_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_tool_executions_task_id_status", "task_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("task_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    command_summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    task: Mapped[ChangeTask] = relationship()
    action: Mapped[AgentAction] = relationship()
    transaction: Mapped[TaskTransaction | None] = relationship()


class BackupEntry(Base):
    __tablename__ = "backup_entries"
    __table_args__ = (
        CheckConstraint("length(original_hash) = 64", name="original_hash_length"),
        CheckConstraint(
            "length(trim(backup_artifact_ref)) > 0", name="backup_artifact_ref_non_empty"
        ),
        CheckConstraint("length(trim(file_type)) > 0", name="file_type_non_empty"),
        CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        Index("ix_backup_entries_task_id_relative_path", "task_id", "relative_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    backup_artifact_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(128), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class FileChange(Base):
    __tablename__ = "file_changes"
    __table_args__ = (
        CheckConstraint(f"change_type IN {_in_values(FileChangeType)}", name="change_type_values"),
        CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        CheckConstraint(
            "before_hash IS NULL OR length(before_hash) = 64", name="before_hash_length"
        ),
        CheckConstraint("after_hash IS NULL OR length(after_hash) = 64", name="after_hash_length"),
        Index("ix_file_changes_tool_execution_id", "tool_execution_id"),
        Index("ix_file_changes_action_id", "action_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tool_execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tool_executions.id", ondelete="RESTRICT"), nullable=False
    )
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="RESTRICT"), nullable=False
    )
    backup_entry_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("backup_entries.id", ondelete="RESTRICT"), nullable=True
    )
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


_COMMITTED_LOCK_INSERT = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_transactions_committed_write_lock_insert
    BEFORE INSERT ON task_transactions
    WHEN NEW.state = 'COMMITTED'
         AND NOT EXISTS (
             SELECT 1 FROM workspace_locks
             WHERE id = NEW.workspace_lock_id
               AND project_id = NEW.project_id
               AND lock_mode = 'WRITE'
               AND status = 'ACTIVE'
         )
    BEGIN
        SELECT RAISE(ABORT, 'COMMITTED transaction requires active WRITE lock');
    END
    """
).execute_if(dialect="sqlite")

_COMMITTED_LOCK_UPDATE = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_transactions_committed_write_lock_update
    BEFORE UPDATE ON task_transactions
    WHEN NEW.state = 'COMMITTED'
         AND NOT EXISTS (
             SELECT 1 FROM workspace_locks
             WHERE id = NEW.workspace_lock_id
               AND project_id = NEW.project_id
               AND lock_mode = 'WRITE'
               AND status = 'ACTIVE'
         )
    BEGIN
        SELECT RAISE(ABORT, 'COMMITTED transaction requires active WRITE lock');
    END
    """
).execute_if(dialect="sqlite")

event.listen(TaskTransaction.__table__, "after_create", _COMMITTED_LOCK_INSERT)
event.listen(TaskTransaction.__table__, "after_create", _COMMITTED_LOCK_UPDATE)
