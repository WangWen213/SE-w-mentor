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
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.governance import GovernanceDecision
from se_mentor.models.llm import AgentAction
from se_mentor.models.task import ChangeTask


class ApprovalRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class ApprovalDecisionOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class ExecutionPolicyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint("id", "proposal_hash", name="uq_approval_requests_id_proposal_hash"),
        CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        CheckConstraint("length(trim(decision_revision)) > 0", name="decision_revision_non_empty"),
        CheckConstraint("length(trim(requested_scope_json)) > 0", name="requested_scope_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        CheckConstraint(f"status IN {_in_values(ApprovalRequestStatus)}", name="status_values"),
        ForeignKeyConstraint(
            ["governance_decision_id", "proposal_hash", "decision_revision"],
            [
                "governance_decisions.id",
                "governance_decisions.proposal_hash",
                "governance_decisions.revision",
            ],
            name="fk_approval_requests_decision_proposal_revision_governance_decisions",
            ondelete="RESTRICT",
        ),
        Index("ix_approval_requests_task_id_status", "task_id", "status"),
        Index("ix_approval_requests_proposal_hash", "proposal_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    governance_decision_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[ChangeTask] = relationship()
    action: Mapped[AgentAction] = relationship()
    governance_decision: Mapped[GovernanceDecision] = relationship()
    decisions: Mapped[list[ApprovalDecision]] = relationship(
        "ApprovalDecision", back_populates="approval_request"
    )
    execution_policies: Mapped[list[ExecutionPolicy]] = relationship(
        "ExecutionPolicy", back_populates="approval_request"
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        CheckConstraint("decision_sequence >= 1", name="decision_sequence_positive"),
        CheckConstraint(f"outcome IN {_in_values(ApprovalDecisionOutcome)}", name="outcome_values"),
        CheckConstraint("length(trim(approver_id)) > 0", name="approver_id_non_empty"),
        CheckConstraint("length(trim(approved_scope_json)) > 0", name="approved_scope_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index(
            "ix_approval_decisions_request_sequence",
            "approval_request_id",
            "decision_sequence",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    approval_request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("approval_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision_sequence: Mapped[int] = mapped_column(nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    approval_request: Mapped[ApprovalRequest] = relationship(back_populates="decisions")


class ExecutionPolicy(Base):
    __tablename__ = "execution_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_request_id", "proposal_hash"],
            ["approval_requests.id", "approval_requests.proposal_hash"],
            name="fk_execution_policies_approval_proposal_approval_requests",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        CheckConstraint(f"status IN {_in_values(ExecutionPolicyStatus)}", name="status_values"),
        CheckConstraint("length(trim(read_paths_json)) > 0", name="read_paths_non_empty"),
        CheckConstraint("length(trim(write_paths_json)) > 0", name="write_paths_non_empty"),
        CheckConstraint("length(trim(protected_paths_json)) > 0", name="protected_paths_non_empty"),
        CheckConstraint("length(trim(commands_json)) > 0", name="commands_non_empty"),
        CheckConstraint("length(trim(network_json)) > 0", name="network_non_empty"),
        CheckConstraint("length(trim(resource_limits_json)) > 0", name="resource_limits_non_empty"),
        CheckConstraint("length(trim(invalidation_json)) > 0", name="invalidation_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_execution_policies_task_id_status", "task_id", "status"),
        Index("ix_execution_policies_proposal_hash_revision", "proposal_hash", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    governance_decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("governance_decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approval_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    executable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    read_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    write_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    protected_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    commands_json: Mapped[str] = mapped_column(Text, nullable=False)
    network_json: Mapped[str] = mapped_column(Text, nullable=False)
    resource_limits_json: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[ChangeTask] = relationship()
    action: Mapped[AgentAction] = relationship()
    governance_decision: Mapped[GovernanceDecision] = relationship()
    approval_request: Mapped[ApprovalRequest | None] = relationship(
        back_populates="execution_policies"
    )


_BLOCK_POLICY_INSERT = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_execution_policies_no_active_block_insert
    BEFORE INSERT ON execution_policies
    WHEN NEW.status = 'ACTIVE' AND NEW.executable = 1
         AND EXISTS (
             SELECT 1 FROM governance_decisions
             WHERE id = NEW.governance_decision_id AND decision = 'BLOCK'
         )
    BEGIN
        SELECT RAISE(ABORT, 'BLOCK governance decision cannot have ACTIVE executable policy');
    END
    """
).execute_if(dialect="sqlite")

_BLOCK_POLICY_UPDATE = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_execution_policies_no_active_block_update
    BEFORE UPDATE ON execution_policies
    WHEN NEW.status = 'ACTIVE' AND NEW.executable = 1
         AND EXISTS (
             SELECT 1 FROM governance_decisions
             WHERE id = NEW.governance_decision_id AND decision = 'BLOCK'
         )
    BEGIN
        SELECT RAISE(ABORT, 'BLOCK governance decision cannot have ACTIVE executable policy');
    END
    """
).execute_if(dialect="sqlite")

event.listen(ExecutionPolicy.__table__, "after_create", _BLOCK_POLICY_INSERT)
event.listen(ExecutionPolicy.__table__, "after_create", _BLOCK_POLICY_UPDATE)
