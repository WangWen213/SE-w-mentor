from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.db.base import Base
from se_mentor.models.llm import AgentAction, RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeProposal, ChangeTask


class ImpactReportStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"


class GovernanceVerdict(StrEnum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class GovernanceDecisionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class GovernanceRuleScope(StrEnum):
    SYSTEM = "SYSTEM"
    PROJECT = "PROJECT"
    TASK = "TASK"


class GovernanceRuleEffect(StrEnum):
    DENY_HARD = "DENY_HARD"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ALLOW = "ALLOW"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class ImpactReport(Base):
    __tablename__ = "impact_reports"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_in_values(ImpactReportStatus)}",
            name="status_values",
        ),
        CheckConstraint("length(trim(direct_impacts_json)) > 0", name="direct_impacts_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_impact_reports_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    base_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direct_impacts_json: Mapped[str] = mapped_column(Text, nullable=False)
    indirect_impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    database_impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainties_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    task: Mapped[ChangeTask] = relationship()
    proposal: Mapped[ChangeProposal] = relationship()
    governance_decisions: Mapped[list[GovernanceDecision]] = relationship(
        "GovernanceDecision",
        back_populates="impact_report",
    )


class GovernanceDecision(Base):
    __tablename__ = "governance_decisions"
    __table_args__ = (
        CheckConstraint(
            f"decision IN {_in_values(GovernanceVerdict)}",
            name="decision_values",
        ),
        CheckConstraint(
            f"risk_level IN {_in_values(RiskLevel)}",
            name="risk_level_values",
        ),
        CheckConstraint(
            f"status IN {_in_values(GovernanceDecisionStatus)}",
            name="status_values",
        ),
        CheckConstraint("length(proposal_hash) = 64", name="proposal_hash_length"),
        CheckConstraint("length(trim(revision)) > 0", name="revision_non_empty"),
        CheckConstraint("length(trim(reason_summary)) > 0", name="reason_summary_non_empty"),
        CheckConstraint("length(trim(rule_set_version)) > 0", name="rule_set_version_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_governance_decisions_proposal_hash", "proposal_hash"),
        Index("ix_governance_decisions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_actions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    impact_report_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("impact_reports.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    allowed_scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    denied_scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[ChangeTask] = relationship()
    action: Mapped[AgentAction | None] = relationship()
    impact_report: Mapped[ImpactReport | None] = relationship(back_populates="governance_decisions")
    rule_hits: Mapped[list[GovernanceRuleHit]] = relationship(
        "GovernanceRuleHit",
        back_populates="decision",
    )


class GovernanceRule(Base):
    __tablename__ = "governance_rules"
    __table_args__ = (
        UniqueConstraint("id", "rule_version", name="uq_governance_rules_id_rule_version"),
        CheckConstraint(
            f"scope_type IN {_in_values(GovernanceRuleScope)}",
            name="scope_type_values",
        ),
        CheckConstraint(
            f"effect IN {_in_values(GovernanceRuleEffect)}",
            name="effect_values",
        ),
        CheckConstraint("priority >= 0", name="priority_non_negative"),
        CheckConstraint("rule_version >= 1", name="rule_version_positive"),
        CheckConstraint("length(trim(rule_key)) > 0", name="rule_key_non_empty"),
        CheckConstraint("length(trim(patterns_json)) > 0", name="patterns_non_empty"),
        CheckConstraint("length(trim(conditions_json)) > 0", name="conditions_non_empty"),
        CheckConstraint(
            "effect != 'DENY_HARD' OR overridable = 0",
            name="deny_hard_not_overridable",
        ),
        Index("ix_governance_rules_rule_key_rule_version", "rule_key", "rule_version", unique=True),
        Index("ix_governance_rules_effect", "effect"),
        Index("ix_governance_rules_priority", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    effect: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    patterns_json: Mapped[str] = mapped_column(Text, nullable=False)
    conditions_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(2048), nullable=False)
    overridable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    project: Mapped[Project | None] = relationship()
    hits: Mapped[list[GovernanceRuleHit]] = relationship("GovernanceRuleHit", back_populates="rule")


class GovernanceRuleHit(Base):
    __tablename__ = "governance_rule_hits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["governance_rules.id", "governance_rules.rule_version"],
            name="fk_governance_rule_hits_rule_version_governance_rules",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"effect IN {_in_values(GovernanceRuleEffect)}",
            name="effect_values",
        ),
        CheckConstraint("rule_version >= 1", name="rule_version_positive"),
        CheckConstraint(
            "length(trim(matched_evidence_json)) > 0", name="matched_evidence_non_empty"
        ),
        Index(
            "ix_governance_rule_hits_decision_rule_version",
            "decision_id",
            "rule_id",
            "rule_version",
            unique=True,
        ),
        Index("ix_governance_rule_hits_rule_id_rule_version", "rule_id", "rule_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("governance_decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    effect: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    decision: Mapped[GovernanceDecision] = relationship(back_populates="rule_hits")
    rule: Mapped[GovernanceRule] = relationship(back_populates="hits")
