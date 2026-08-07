from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, exc, inspect, select, text

from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskIteration,
    TaskIterationPhase,
    TaskIterationResult,
    TaskStatus,
)


def test_T010_change_task_round_trip_status_fk_and_counts_are_constrained(
    tmp_path: Path,
) -> None:
    engine = _create_schema(tmp_path / "task-domain.sqlite3")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            requester_id="user-1",
            original_request="Add a persistence model for change tasks.",
            base_revision="8018128",
            base_workspace_hash="workspace-hash",
            status=TaskStatus.CREATED,
            current_step="created",
            iteration_count=0,
            repair_count=0,
            stagnation_count=0,
            version=1,
        )
        session.add(task)
        session.flush()
        task_id = task.id

    with session_scope(session_factory) as session:
        reloaded = session.get(ChangeTask, task_id)
        assert reloaded is not None
        assert reloaded.project is not None
        assert reloaded.original_request == "Add a persistence model for change tasks."
        assert reloaded.status == TaskStatus.CREATED
        assert reloaded.iteration_count == 0

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(ChangeTask(project_id="missing-project", original_request="orphan task"))

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO change_tasks (
                id, project_id, original_request, status, iteration_count, repair_count,
                stagnation_count, version, created_at, updated_at
            )
            VALUES (
                'bad-status', :project_id, 'bad status', 'NOT_A_TASK_STATUS', 0, 0,
                0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"project_id": _project_id(engine)},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO change_tasks (
                id, project_id, original_request, status, iteration_count, repair_count,
                stagnation_count, version, created_at, updated_at
            )
            VALUES (
                'bad-counts', :project_id, 'bad counts', 'CREATED', -1, 0,
                0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"project_id": _project_id(engine)},
        )


def test_T010_proposal_v1_cannot_be_overwritten_and_negative_counts_fail(
    tmp_path: Path,
) -> None:
    engine = _create_schema(tmp_path / "proposal-domain.sqlite3")
    session_factory = create_session_factory(engine)
    task_id = _insert_task(session_factory, tmp_path)

    with session_scope(session_factory) as session:
        first = ChangeProposal(
            task_id=task_id,
            version=1,
            goal="Persist task proposals.",
            current_problem="No proposal model exists.",
            expected_behavior="Proposal versions are immutable records.",
            initial_scope_json='["backend/src/se_mentor/models/task.py"]',
            excluded_scope_json="[]",
            constraints_json='["no service workflow"]',
            assumptions_json="[]",
            risks_json="[]",
            acceptance_criteria_json='["version uniqueness is enforced"]',
            validation_plan_json='["pytest backend/tests/models/test_task_models.py"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.CONFIRMED,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        second = ChangeProposal(
            task_id=task_id,
            version=2,
            goal="Persist task proposals v2.",
            expected_behavior="Older proposal remains addressable.",
            initial_scope_json='["backend/src/se_mentor/models/task.py"]',
            acceptance_criteria_json='["supersedes relation is persisted"]',
            completeness=ProposalCompleteness.PARTIALLY_COMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
            supersedes=first,
        )
        session.add_all([first, second])
        session.flush()
        second_id = second.id

    with session_scope(session_factory) as session:
        reloaded = session.get(ChangeProposal, second_id)
        assert reloaded is not None
        assert reloaded.task_id == task_id
        assert reloaded.version == 2
        assert reloaded.supersedes is not None
        assert reloaded.supersedes.version == 1
        assert reloaded.status == ProposalStatus.DRAFT

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            ChangeProposal(
                task_id=task_id,
                version=1,
                goal="Duplicate proposal version.",
                expected_behavior="Rejected.",
                initial_scope_json="[]",
                acceptance_criteria_json="[]",
                completeness=ProposalCompleteness.INCOMPLETE,
                status=ProposalStatus.DRAFT,
                created_by_type=ProposalCreatedByType.USER,
            )
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO change_proposals (
                id, task_id, version, goal, expected_behavior, initial_scope_json,
                acceptance_criteria_json, completeness, status, created_by_type, created_at
            )
            VALUES (
                'bad-version', :task_id, 0, 'bad', 'bad', '[]', '[]',
                'INCOMPLETE', 'DRAFT', 'SYSTEM', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": task_id},
        )


def test_T010_task_iteration_round_trip_and_numbers_are_constrained(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "iteration-domain.sqlite3")
    session_factory = create_session_factory(engine)
    task_id = _insert_task(session_factory, tmp_path)

    with session_scope(session_factory) as session:
        iteration = TaskIteration(
            task_id=task_id,
            iteration_number=1,
            phase=TaskIterationPhase.ANALYZE,
            context_token_count=1200,
            result=TaskIterationResult.PROGRESS,
            progress_score=Decimal("0.75"),
        )
        session.add(iteration)
        session.flush()
        iteration_id = iteration.id

    with session_scope(session_factory) as session:
        reloaded = session.get(TaskIteration, iteration_id)

    assert reloaded is not None
    assert reloaded.task_id == task_id
    assert reloaded.iteration_number == 1
    assert reloaded.phase == TaskIterationPhase.ANALYZE
    assert reloaded.result == TaskIterationResult.PROGRESS

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            TaskIteration(
                task_id=task_id,
                iteration_number=1,
                phase=TaskIterationPhase.EXECUTE,
            )
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO task_iterations (
                id, task_id, iteration_number, phase, started_at
            )
            VALUES (
                'bad-iteration', :task_id, 0, 'ANALYZE', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": task_id},
        )


def test_T010_task_schema_indexes_and_migration_match_the_orm(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "schema-parity.sqlite3")
    inspector = inspect(engine)

    assert {
        "change_tasks",
        "change_proposals",
        "task_iterations",
    }.issubset(inspector.get_table_names())
    assert {
        "ix_change_tasks_project_id",
        "ix_change_tasks_status",
        "ix_change_tasks_created_at",
    }.issubset(_index_names(engine, "change_tasks"))
    assert {
        "ix_change_proposals_task_id",
        "ix_change_proposals_task_id_version",
        "ix_change_proposals_supersedes_id",
    }.issubset(_index_names(engine, "change_proposals"))
    assert {
        "ix_task_iterations_task_id",
        "ix_task_iterations_task_id_iteration_number",
    }.issubset(_index_names(engine, "task_iterations"))
    assert {
        "ck_change_tasks_status_values",
        "ck_change_tasks_iteration_count_non_negative",
        "ck_change_tasks_repair_count_non_negative",
        "ck_change_tasks_stagnation_count_non_negative",
        "ck_change_tasks_version_positive",
    }.issubset(_check_constraint_names(engine, "change_tasks"))
    assert {
        "ck_change_proposals_version_positive",
        "ck_change_proposals_completeness_values",
        "ck_change_proposals_status_values",
        "ck_change_proposals_created_by_type_values",
    }.issubset(_check_constraint_names(engine, "change_proposals"))
    assert {
        "ck_task_iterations_iteration_number_positive",
        "ck_task_iterations_phase_values",
        "ck_task_iterations_context_token_count_non_negative",
        "ck_task_iterations_result_values",
    }.issubset(_check_constraint_names(engine, "task_iterations"))

    backend_dir = Path(__file__).resolve().parents[2]
    migration_text = (backend_dir / "migrations/versions/0020_task_domain.py").read_text(
        encoding="utf-8"
    )
    for expected_fragment in (
        'revision = "0020_task_domain"',
        'down_revision = "0010_project_domain"',
        "ck_change_tasks_status_values",
        "ck_change_proposals_version_positive",
        "ck_task_iterations_iteration_number_positive",
    ):
        assert expected_fragment in migration_text


def _create_schema(database_path: Path) -> Engine:
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    return engine


def _insert_task(session_factory: Any, tmp_path: Path) -> str:
    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Implement task domain persistence.",
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        return task.id


def _project_id(engine: Engine) -> str:
    with engine.connect() as connection:
        value = connection.execute(select(Project.id)).scalar_one()
    return str(value)


def _execute(engine: Engine, statement: str, parameters: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement), parameters)


def _index_names(engine: Engine, table_name: str) -> set[str]:
    return {
        name
        for index in inspect(engine).get_indexes(table_name)
        if (name := index["name"]) is not None
    }


def _check_constraint_names(engine: Engine, table_name: str) -> set[str]:
    return {
        name
        for constraint in inspect(engine).get_check_constraints(table_name)
        if (name := constraint["name"]) is not None
    }
