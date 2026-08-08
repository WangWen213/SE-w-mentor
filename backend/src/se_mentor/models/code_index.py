from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.project import Project


class CodeIndexStatus(StrEnum):
    BUILDING = "BUILDING"
    READY = "READY"
    STALE = "STALE"
    FAILED = "FAILED"


class CodeSymbolKind(StrEnum):
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    API = "API"
    DTO = "DTO"
    TABLE = "TABLE"
    TEST = "TEST"


class CodeSymbolRelationType(StrEnum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    TESTS = "TESTS"
    SERIALIZES = "SERIALIZES"
    READS_TABLE = "READS_TABLE"
    WRITES_TABLE = "WRITES_TABLE"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class CodeIndex(Base):
    __tablename__ = "code_indexes"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "revision", "language", name="uq_code_indexes_project_revision_language"
        ),
        CheckConstraint(f"status IN {_in_values(CodeIndexStatus)}", name="status_values"),
        CheckConstraint("index_generation >= 1", name="index_generation_positive"),
        CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        CheckConstraint("length(trim(language)) > 0", name="language_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_code_indexes_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    index_generation: Mapped[int] = mapped_column(nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship()
    symbols: Mapped[list[CodeSymbol]] = relationship("CodeSymbol", back_populates="code_index")


class CodeSymbol(Base):
    __tablename__ = "code_symbols"
    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", "revision", name="uq_code_symbols_id_project_revision"
        ),
        UniqueConstraint("code_index_id", "symbol_key", name="uq_code_symbols_index_symbol_key"),
        CheckConstraint(f"kind IN {_in_values(CodeSymbolKind)}", name="kind_values"),
        CheckConstraint("length(trim(symbol_key)) > 0", name="symbol_key_non_empty"),
        CheckConstraint("length(trim(qualified_name)) > 0", name="qualified_name_non_empty"),
        CheckConstraint("length(trim(relative_path)) > 0", name="relative_path_non_empty"),
        Index("ix_code_symbols_project_revision_kind", "project_id", "revision", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    code_index_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("code_indexes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(512), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    signature_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    code_index: Mapped[CodeIndex] = relationship(back_populates="symbols")


class CodeSymbolRelation(Base):
    __tablename__ = "code_symbol_relations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_symbol_id", "source_project_id", "source_revision"],
            ["code_symbols.id", "code_symbols.project_id", "code_symbols.revision"],
            name="fk_code_symbol_relations_source_symbol_project_revision_code_symbols",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_symbol_id", "target_project_id", "target_revision"],
            ["code_symbols.id", "code_symbols.project_id", "code_symbols.revision"],
            name="fk_code_symbol_relations_target_symbol_project_revision_code_symbols",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_symbol_id",
            "target_symbol_id",
            "relation_type",
            name="uq_code_symbol_relations_source_target_type",
        ),
        CheckConstraint(
            f"relation_type IN {_in_values(CodeSymbolRelationType)}", name="relation_type_values"
        ),
        CheckConstraint("source_project_id = target_project_id", name="same_project"),
        CheckConstraint("source_revision = target_revision", name="same_revision"),
        CheckConstraint("source_symbol_id != target_symbol_id", name="no_self_relation"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_code_symbol_relations_source", "source_symbol_id"),
        Index("ix_code_symbol_relations_target", "target_symbol_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_symbol_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    target_symbol_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
