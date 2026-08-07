from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.contracts.enums import ActionType
from se_mentor.db.base import Base
from se_mentor.models.task import ChangeTask, TaskIteration

FORBIDDEN_LLM_PERSISTENCE_FIELDS = {
    "api_key",
    "token_secret",
    "provider_secret",
    "authorization_header",
    "raw_headers",
    "credentials",
    "password",
    "secret",
    "prompt",
    "response",
    "raw_prompt",
    "raw_response",
    "conversation",
    "raw_arguments",
    "full_arguments",
    "tool_payload",
}


class LLMCallStatus(StrEnum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class ParseStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AgentActionStatus(StrEnum):
    PARSED = "PARSED"
    GOVERNING = "GOVERNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_in_values(LLMCallStatus)}",
            name="status_values",
        ),
        CheckConstraint(
            f"parse_status IN {_in_values(ParseStatus)}",
            name="parse_status_values",
        ),
        CheckConstraint("input_tokens >= 0", name="input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_non_negative"),
        CheckConstraint("compression_count >= 0", name="compression_count_non_negative"),
        CheckConstraint("retry_count >= 0", name="retry_count_non_negative"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="latency_ms_non_negative",
        ),
        Index("ix_llm_calls_provider_name", "provider_name"),
        Index("ix_llm_calls_model_name", "model_name"),
        Index("ix_llm_calls_parse_status", "parse_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    iteration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_iterations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_summary: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    response_summary: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    compression_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    iteration: Mapped[TaskIteration] = relationship(back_populates="llm_calls")
    agent_actions: Mapped[list[AgentAction]] = relationship(
        "AgentAction", back_populates="llm_call"
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __init__(self, **kwargs: Any) -> None:
        forbidden = FORBIDDEN_LLM_PERSISTENCE_FIELDS.intersection(kwargs)
        if forbidden:
            raise TypeError(f"unsafe LLM persistence fields are not stored: {sorted(forbidden)}")
        super().__init__(**kwargs)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in FORBIDDEN_LLM_PERSISTENCE_FIELDS:
            raise AttributeError(f"unsafe LLM persistence field is not stored: {key}")
        super().__setattr__(key, value)


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        CheckConstraint("action_sequence >= 1", name="action_sequence_positive"),
        CheckConstraint(
            f"action_type IN {_in_values(ActionType)}",
            name="action_type_values",
        ),
        CheckConstraint(
            f"parse_status IN {_in_values(ParseStatus)}",
            name="parse_status_values",
        ),
        CheckConstraint(
            f"risk_level IS NULL OR risk_level IN {_in_values(RiskLevel)}",
            name="risk_level_values",
        ),
        CheckConstraint(
            f"status IN {_in_values(AgentActionStatus)}",
            name="status_values",
        ),
        Index(
            "ix_agent_actions_iteration_id_action_sequence",
            "iteration_id",
            "action_sequence",
            unique=True,
        ),
        Index("ix_agent_actions_action_type", "action_type"),
        Index("ix_agent_actions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    iteration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_iterations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    llm_call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("llm_calls.id", ondelete="RESTRICT"),
        nullable=True,
    )
    action_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters_summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    parameters_artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    task: Mapped[ChangeTask] = relationship()
    iteration: Mapped[TaskIteration] = relationship(back_populates="agent_actions")
    llm_call: Mapped[LLMCall | None] = relationship(back_populates="agent_actions")

    def __init__(self, **kwargs: Any) -> None:
        forbidden = FORBIDDEN_LLM_PERSISTENCE_FIELDS.intersection(kwargs)
        if forbidden:
            raise TypeError(f"unsafe action persistence fields are not stored: {sorted(forbidden)}")
        super().__init__(**kwargs)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in FORBIDDEN_LLM_PERSISTENCE_FIELDS:
            raise AttributeError(f"unsafe action persistence field is not stored: {key}")
        super().__setattr__(key, value)
