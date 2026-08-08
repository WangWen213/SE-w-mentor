from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    GovernanceVerdict,
)
from se_mentor.models.llm import AgentAction, AgentActionStatus, ParseStatus, RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskIteration,
    TaskIterationPhase,
    TaskStatus,
)

PROPOSAL_HASH = "a" * 64
REVISION = "phase1-revision"


def create_schema(database_path: Path) -> Engine:
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    return engine


def execute(engine: Engine, statement: str, parameters: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement), parameters)


def seed_task_graph(engine: Engine, tmp_path: Path) -> dict[str, str]:
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Persist Phase 1 schema facts.",
            base_revision=REVISION,
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        proposal = ChangeProposal(
            task_id=task.id,
            version=1,
            goal="Persist Phase 1 schema.",
            expected_behavior="Phase 1 facts remain auditable.",
            initial_scope_json='["backend/src/se_mentor/models"]',
            acceptance_criteria_json='["schema constraints hold"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.CONFIRMED,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        session.add(proposal)
        session.flush()
        iteration = TaskIteration(
            task_id=task.id,
            iteration_number=1,
            phase=TaskIterationPhase.ANALYZE,
        )
        session.add(iteration)
        session.flush()
        action = AgentAction(
            task_id=task.id,
            iteration_id=iteration.id,
            action_sequence=1,
            action_type="APPLY_PATCH",
            parameters_summary="schema patch",
            schema_version="v1",
            parse_status=ParseStatus.VALID,
            risk_level=RiskLevel.MEDIUM,
            status=AgentActionStatus.PARSED,
            idempotency_key=f"phase1-{task.id}",
        )
        session.add(action)
        session.flush()
        decision = GovernanceDecision(
            task_id=task.id,
            action_id=action.id,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            decision=GovernanceVerdict.WARN,
            risk_level=RiskLevel.MEDIUM,
            reason_summary="approval required",
            approval_required=True,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version="phase1-rules-v1",
            evidence_json='[{"source":"phase1","summary":"decision"}]',
        )
        session.add(decision)
        blocked = GovernanceDecision(
            task_id=task.id,
            action_id=action.id,
            proposal_hash="b" * 64,
            revision=REVISION,
            decision=GovernanceVerdict.BLOCK,
            risk_level=RiskLevel.CRITICAL,
            reason_summary="blocked",
            approval_required=True,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version="phase1-rules-v1",
            evidence_json='[{"source":"phase1","summary":"blocked"}]',
        )
        session.add(blocked)
        session.flush()
        return {
            "project_id": project.id,
            "task_id": task.id,
            "proposal_id": proposal.id,
            "iteration_id": iteration.id,
            "action_id": action.id,
            "decision_id": decision.id,
            "blocked_decision_id": blocked.id,
        }


def row_count(engine: Engine, table_name: str) -> int:
    with engine.begin() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def as_any(value: object) -> Any:
    return value
