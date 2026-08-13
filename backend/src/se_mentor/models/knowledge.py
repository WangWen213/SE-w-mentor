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
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.project import Project


class KnowledgeStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    REVIEWED = "REVIEWED"
    FAILED_EXPERIENCE = "FAILED_EXPERIENCE"
    CONFLICTING = "CONFLICTING"
    DEPRECATED = "DEPRECATED"
    STALE = "STALE"


class KnowledgeType(StrEnum):
    PATTERN = "PATTERN"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    FAILURE = "FAILURE"


class KnowledgeSourceType(StrEnum):
    LLM_SUMMARY = "LLM_SUMMARY"
    TEST = "TEST"
    USER_REVIEW = "USER_REVIEW"
    COMMITTED_DIFF = "COMMITTED_DIFF"
    GOVERNANCE_AUDIT = "GOVERNANCE_AUDIT"


class KnowledgeRelationType(StrEnum):
    SUPERSEDES = "SUPERSEDES"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SUPPORTS = "SUPPORTS"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class EngineeringKnowledge(Base):
    __tablename__ = "engineering_knowledge"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "knowledge_key",
            "version",
            name="uq_engineering_knowledge_project_key_version",
        ),
        CheckConstraint(
            f"knowledge_type IN {_in_values(KnowledgeType)}", name="knowledge_type_values"
        ),
        CheckConstraint(f"status IN {_in_values(KnowledgeStatus)}", name="status_values"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("length(trim(knowledge_key)) > 0", name="knowledge_key_non_empty"),
        CheckConstraint("length(trim(scope_json)) > 0", name="scope_non_empty"),
        CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        CheckConstraint(
            "status != 'VERIFIED' OR "
            "(verified_evidence_json IS NOT NULL AND length(trim(verified_evidence_json)) > 0)",
            name="verified_requires_evidence",
        ),
        Index(
            "ix_engineering_knowledge_project_type_status", "project_id", "knowledge_type", "status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    knowledge_key: Mapped[str] = mapped_column(String(256), nullable=False)
    knowledge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    verified_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship()
    signatures: Mapped[list[KnowledgeSignature]] = relationship(
        "KnowledgeSignature", back_populates="knowledge"
    )
    sources: Mapped[list[KnowledgeSource]] = relationship(
        "KnowledgeSource", back_populates="knowledge"
    )


class KnowledgeSignature(Base):
    __tablename__ = "knowledge_signatures"
    __table_args__ = (
        CheckConstraint("length(signature_hash) = 64", name="signature_hash_length"),
        Index("ix_knowledge_signatures_signature_hash", "signature_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("engineering_knowledge.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    knowledge: Mapped[EngineeringKnowledge] = relationship(back_populates="signatures")


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint(
            f"source_type IN {_in_values(KnowledgeSourceType)}", name="source_type_values"
        ),
        CheckConstraint("length(trim(source_ref)) > 0", name="source_ref_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_knowledge_sources_knowledge_type", "knowledge_id", "source_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("engineering_knowledge.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    knowledge: Mapped[EngineeringKnowledge] = relationship(back_populates="sources")


class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_knowledge_id",
            "target_knowledge_id",
            "relation_type",
            name="uq_knowledge_relations_source_target_type",
        ),
        CheckConstraint(
            f"relation_type IN {_in_values(KnowledgeRelationType)}", name="relation_type_values"
        ),
        CheckConstraint("source_knowledge_id != target_knowledge_id", name="no_self_relation"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_knowledge_relations_project_type", "project_id", "relation_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("engineering_knowledge.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("engineering_knowledge.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


_RELATION_PROJECT_INSERT = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_knowledge_relations_project_insert
    BEFORE INSERT ON knowledge_relations
    WHEN NOT EXISTS (
        SELECT 1
        FROM engineering_knowledge source
        JOIN engineering_knowledge target ON target.id = NEW.target_knowledge_id
        WHERE source.id = NEW.source_knowledge_id
          AND source.project_id = NEW.project_id
          AND target.project_id = NEW.project_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'knowledge relation cannot cross project');
    END
    """
).execute_if(dialect="sqlite")

_RELATION_PROJECT_UPDATE = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER IF NOT EXISTS trg_knowledge_relations_project_update
    BEFORE UPDATE ON knowledge_relations
    WHEN NOT EXISTS (
        SELECT 1
        FROM engineering_knowledge source
        JOIN engineering_knowledge target ON target.id = NEW.target_knowledge_id
        WHERE source.id = NEW.source_knowledge_id
          AND source.project_id = NEW.project_id
          AND target.project_id = NEW.project_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'knowledge relation cannot cross project');
    END
    """
).execute_if(dialect="sqlite")

event.listen(KnowledgeRelation.__table__, "after_create", _RELATION_PROJECT_INSERT)
event.listen(KnowledgeRelation.__table__, "after_create", _RELATION_PROJECT_UPDATE)
