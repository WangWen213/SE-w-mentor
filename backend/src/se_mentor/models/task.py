from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.project import Project

if TYPE_CHECKING:
    from se_mentor.models.llm import AgentAction, LLMCall


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    WAITING_FOR_LOCK = "WAITING_FOR_LOCK"
    INITIALIZING = "INITIALIZING"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    DECIDING = "DECIDING"
    PROPOSAL_REVIEW = "PROPOSAL_REVIEW"
    GOVERNING = "GOVERNING"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ACTION_PENDING = "ACTION_PENDING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    STAGNATION_WARNING = "STAGNATION_WARNING"
    PAUSED = "PAUSED"
    KNOWLEDGE_UPDATING = "KNOWLEDGE_UPDATING"
    ROLLING_BACK = "ROLLING_BACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ProposalCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIALLY_COMPLETE = "PARTIALLY_COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    CONFLICTING = "CONFLICTING"


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ProposalCreatedByType(StrEnum):
    LLM = "LLM"
    USER = "USER"
    SYSTEM = "SYSTEM"


class TaskIterationPhase(StrEnum):
    ANALYZE = "ANALYZE"
    EXECUTE = "EXECUTE"
    REPAIR = "REPAIR"


class TaskIterationResult(StrEnum):
    PROGRESS = "PROGRESS"
    NO_PROGRESS = "NO_PROGRESS"
    ERROR = "ERROR"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


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


class ChangeTask(TimestampMixin, Base):
    __tablename__ = "change_tasks"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_in_values(TaskStatus)}",
            name="status_values",
        ),
        CheckConstraint("iteration_count >= 0", name="iteration_count_non_negative"),
        CheckConstraint("repair_count >= 0", name="repair_count_non_negative"),
        CheckConstraint("stagnation_count >= 0", name="stagnation_count_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_change_tasks_status", "status"),
        Index("ix_change_tasks_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requester_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_request: Mapped[str] = mapped_column(Text, nullable=False)
    base_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_workspace_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.CREATED)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_lock_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stagnation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="tasks")
    proposals: Mapped[list[ChangeProposal]] = relationship(back_populates="task")
    iterations: Mapped[list[TaskIteration]] = relationship(back_populates="task")


class ChangeProposal(TimestampMixin, Base):
    __tablename__ = "change_proposals"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            f"completeness IN {_in_values(ProposalCompleteness)}",
            name="completeness_values",
        ),
        CheckConstraint(
            f"status IN {_in_values(ProposalStatus)}",
            name="status_values",
        ),
        CheckConstraint(
            f"created_by_type IN {_in_values(ProposalCreatedByType)}",
            name="created_by_type_values",
        ),
        Index("ix_change_proposals_task_id_version", "task_id", "version", unique=True),
        Index("ix_change_proposals_supersedes_id", "supersedes_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    current_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    initial_scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria_json: Mapped[str] = mapped_column(Text, nullable=False)
    validation_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    completeness: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProposalCompleteness.INCOMPLETE,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ProposalStatus.DRAFT)
    created_by_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProposalCreatedByType.SYSTEM,
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("change_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )

    task: Mapped[ChangeTask] = relationship(back_populates="proposals")
    supersedes: Mapped[ChangeProposal | None] = relationship(
        remote_side="ChangeProposal.id",
        foreign_keys=[supersedes_id],
    )


class TaskIteration(TimestampMixin, Base):
    __tablename__ = "task_iterations"
    __table_args__ = (
        CheckConstraint("iteration_number >= 1", name="iteration_number_positive"),
        CheckConstraint(
            f"phase IN {_in_values(TaskIterationPhase)}",
            name="phase_values",
        ),
        CheckConstraint(
            "context_token_count IS NULL OR context_token_count >= 0",
            name="context_token_count_non_negative",
        ),
        CheckConstraint(
            f"result IS NULL OR result IN {_in_values(TaskIterationResult)}",
            name="result_values",
        ),
        Index(
            "ix_task_iterations_task_id_iteration_number",
            "task_id",
            "iteration_number",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    context_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    progress_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    task: Mapped[ChangeTask] = relationship(back_populates="iterations")
    llm_calls: Mapped[list[LLMCall]] = relationship("LLMCall", back_populates="iteration")
    agent_actions: Mapped[list[AgentAction]] = relationship(
        "AgentAction",
        back_populates="iteration",
    )
