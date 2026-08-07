from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, exc, inspect, text

from se_mentor.contracts.enums import ActionType
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.models.llm import (
    AgentAction,
    AgentActionStatus,
    LLMCall,
    LLMCallStatus,
    ParseStatus,
    RiskLevel,
)
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask, TaskIteration, TaskIterationPhase, TaskStatus

SECRET_SENTINEL = "T011_FAKE_SECRET_DO_NOT_PERSIST"


def test_T011_llm_call_requires_model_token_and_parse_status(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "llm-call.sqlite3")
    session_factory = create_session_factory(engine)
    _task_id, iteration_id = _insert_iteration(session_factory, tmp_path)

    with session_scope(session_factory) as session:
        call = LLMCall(
            iteration_id=iteration_id,
            provider_name="openai",
            model_name="gpt-5",
            request_summary="redacted request summary",
            response_summary="redacted response summary",
            input_tokens=1200,
            output_tokens=300,
            compression_count=1,
            status=LLMCallStatus.SUCCESS,
            retry_count=0,
            latency_ms=850,
            parse_status=ParseStatus.VALID,
        )
        session.add(call)
        session.flush()
        call_id = call.id

    with session_scope(session_factory) as session:
        reloaded = session.get(LLMCall, call_id)

    assert reloaded is not None
    assert reloaded.iteration_id == iteration_id
    assert reloaded.provider_name == "openai"
    assert reloaded.model_name == "gpt-5"
    assert reloaded.input_tokens == 1200
    assert reloaded.output_tokens == 300
    assert reloaded.total_tokens == 1500
    assert reloaded.latency_ms == 850
    assert reloaded.parse_status == ParseStatus.VALID

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO llm_calls (
                id, iteration_id, provider_name, model_name, input_tokens, output_tokens,
                compression_count, status, retry_count, parse_status, created_at
            )
            VALUES (
                'missing-model', :iteration_id, 'openai', NULL, 1, 1,
                0, 'SUCCESS', 0, 'VALID', CURRENT_TIMESTAMP
            )
            """,
            {"iteration_id": iteration_id},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO llm_calls (
                id, iteration_id, provider_name, model_name, input_tokens, output_tokens,
                compression_count, status, retry_count, parse_status, created_at
            )
            VALUES (
                'missing-token', :iteration_id, 'openai', 'gpt-5', NULL, 1,
                0, 'SUCCESS', 0, 'VALID', CURRENT_TIMESTAMP
            )
            """,
            {"iteration_id": iteration_id},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO llm_calls (
                id, iteration_id, provider_name, model_name, input_tokens, output_tokens,
                compression_count, status, retry_count, latency_ms, parse_status, created_at
            )
            VALUES (
                'bad-values', :iteration_id, 'openai', 'gpt-5', -1, 1,
                0, 'SUCCESS', 0, -1, 'NOT_A_PARSE_STATUS', CURRENT_TIMESTAMP
            )
            """,
            {"iteration_id": iteration_id},
        )


def test_T011_agent_action_round_trip_sequence_uniqueness_and_fk(tmp_path: Path) -> None:
    engine = _create_schema(tmp_path / "agent-action.sqlite3")
    session_factory = create_session_factory(engine)
    task_id, iteration_id = _insert_iteration(session_factory, tmp_path)
    _second_task_id, second_iteration_id = _insert_iteration(
        session_factory,
        tmp_path / "second",
    )
    llm_call_id = _insert_llm_call(session_factory, iteration_id)

    with session_scope(session_factory) as session:
        first = AgentAction(
            task_id=task_id,
            iteration_id=iteration_id,
            llm_call_id=llm_call_id,
            action_sequence=1,
            action_type=ActionType.READ_FILE,
            parameters_summary="read README path only",
            parameters_artifact_ref="artifact://actions/readme-summary",
            schema_version="agent-action.v1",
            parse_status=ParseStatus.VALID,
            risk_level=RiskLevel.LOW,
            status=AgentActionStatus.PARSED,
            idempotency_key="T011-action-1",
        )
        second = AgentAction(
            task_id=task_id,
            iteration_id=iteration_id,
            action_sequence=2,
            action_type=ActionType.SEARCH_CODE,
            parameters_summary="search for model registry usage",
            schema_version="agent-action.v1",
            parse_status=ParseStatus.VALID,
            status=AgentActionStatus.PARSED,
            idempotency_key="T011-action-2",
        )
        same_sequence_other_iteration = AgentAction(
            task_id=_second_task_id,
            iteration_id=second_iteration_id,
            action_sequence=1,
            action_type=ActionType.READ_FILE,
            parameters_summary="same sequence in another iteration is allowed",
            schema_version="agent-action.v1",
            parse_status=ParseStatus.VALID,
            status=AgentActionStatus.PARSED,
            idempotency_key="T011-action-3",
        )
        session.add_all([first, second, same_sequence_other_iteration])
        session.flush()
        first_id = first.id

    with session_scope(session_factory) as session:
        reloaded = session.get(AgentAction, first_id)
        assert reloaded is not None
        assert reloaded.iteration_id == iteration_id
        assert reloaded.llm_call_id == llm_call_id
        assert reloaded.action_sequence == 1
        assert reloaded.action_type == ActionType.READ_FILE
        assert reloaded.parameters_summary == "read README path only"
        assert reloaded.status == AgentActionStatus.PARSED

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            AgentAction(
                task_id=task_id,
                iteration_id=iteration_id,
                action_sequence=1,
                action_type=ActionType.RUN_COMMAND,
                parameters_summary="duplicate sequence",
                schema_version="agent-action.v1",
                parse_status=ParseStatus.VALID,
                status=AgentActionStatus.PARSED,
                idempotency_key="T011-action-duplicate-sequence",
            )
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO agent_actions (
                id, task_id, iteration_id, action_sequence, action_type, parameters_summary,
                schema_version, parse_status, status, idempotency_key, created_at
            )
            VALUES (
                'bad-action-fk', 'missing-task', 'missing-iteration', 1, 'READ_FILE',
                'summary', 'agent-action.v1', 'VALID', 'PARSED',
                'T011-bad-action-fk', CURRENT_TIMESTAMP
            )
            """,
            {},
        )

    with pytest.raises(exc.IntegrityError):
        _execute(
            engine,
            """
            INSERT INTO agent_actions (
                id, task_id, iteration_id, action_sequence, action_type, parameters_summary,
                schema_version, parse_status, status, idempotency_key, created_at
            )
            VALUES (
                'bad-action-contract', :task_id, :iteration_id, 0, 'NOT_AN_ACTION',
                'summary', 'agent-action.v1', 'VALID', 'NOT_A_STATUS',
                'T011-bad-action-contract', CURRENT_TIMESTAMP
            )
            """,
            {"task_id": task_id, "iteration_id": iteration_id},
        )


def test_T011_llm_and_action_reject_unbounded_prompt_and_secret_sinks(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "bounded-storage.sqlite3"
    engine = _create_schema(database_path)
    session_factory = create_session_factory(engine)
    task_id, iteration_id = _insert_iteration(session_factory, tmp_path)

    with pytest.raises(TypeError):
        LLMCall(
            iteration_id=iteration_id,
            provider_name="openai",
            model_name="gpt-5",
            input_tokens=1,
            output_tokens=1,
            status=LLMCallStatus.SUCCESS,
            parse_status=ParseStatus.VALID,
            api_key=SECRET_SENTINEL,
        )

    with pytest.raises(TypeError):
        AgentAction(
            task_id=task_id,
            iteration_id=iteration_id,
            action_sequence=1,
            action_type=ActionType.READ_FILE,
            parameters_summary="safe",
            schema_version="agent-action.v1",
            parse_status=ParseStatus.VALID,
            status=AgentActionStatus.PARSED,
            idempotency_key="T011-secret-action",
            raw_arguments=SECRET_SENTINEL,
        )

    with session_scope(session_factory) as session:
        call = LLMCall(
            iteration_id=iteration_id,
            provider_name="openai",
            model_name="gpt-5",
            request_summary="redacted request summary",
            response_summary="redacted response summary",
            input_tokens=1,
            output_tokens=1,
            status=LLMCallStatus.SUCCESS,
            parse_status=ParseStatus.VALID,
        )
        session.add(call)
        session.flush()
        session.add(
            AgentAction(
                task_id=task_id,
                iteration_id=iteration_id,
                llm_call_id=call.id,
                action_sequence=1,
                action_type=ActionType.READ_FILE,
                parameters_summary="redacted action parameter summary",
                schema_version="agent-action.v1",
                parse_status=ParseStatus.VALID,
                status=AgentActionStatus.PARSED,
                idempotency_key="T011-safe-action",
            )
        )

    forbidden_column_names = {
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
    assert _column_names(engine, "llm_calls").isdisjoint(forbidden_column_names)
    assert _column_names(engine, "agent_actions").isdisjoint(forbidden_column_names)
    assert SECRET_SENTINEL not in _sqlite_dump(database_path)


def test_T011_migrated_schema_matches_the_orm(tmp_path: Path) -> None:
    orm_engine = _create_schema(tmp_path / "orm.sqlite3")
    migrated_engine = _create_migrated_schema(tmp_path / "migrated.sqlite3")

    for engine in (orm_engine, migrated_engine):
        inspector = inspect(engine)
        assert {"llm_calls", "agent_actions"}.issubset(inspector.get_table_names())
        assert {
            "ix_llm_calls_iteration_id",
            "ix_llm_calls_provider_name",
            "ix_llm_calls_model_name",
            "ix_llm_calls_parse_status",
        }.issubset(_index_names(engine, "llm_calls"))
        assert {
            "ix_agent_actions_iteration_id",
            "ix_agent_actions_iteration_id_action_sequence",
            "ix_agent_actions_action_type",
            "ix_agent_actions_status",
        }.issubset(_index_names(engine, "agent_actions"))
        assert {
            "ck_llm_calls_status_values",
            "ck_llm_calls_parse_status_values",
            "ck_llm_calls_input_tokens_non_negative",
            "ck_llm_calls_output_tokens_non_negative",
            "ck_llm_calls_compression_count_non_negative",
            "ck_llm_calls_retry_count_non_negative",
            "ck_llm_calls_latency_ms_non_negative",
        }.issubset(_check_constraint_names(engine, "llm_calls"))
        assert {
            "ck_agent_actions_action_sequence_positive",
            "ck_agent_actions_action_type_values",
            "ck_agent_actions_parse_status_values",
            "ck_agent_actions_risk_level_values",
            "ck_agent_actions_status_values",
        }.issubset(_check_constraint_names(engine, "agent_actions"))
        assert _foreign_key_ondelete(engine, "llm_calls", "iteration_id") == "RESTRICT"
        assert _foreign_key_ondelete(engine, "agent_actions", "iteration_id") == "RESTRICT"
        assert _foreign_key_ondelete(engine, "agent_actions", "llm_call_id") == "RESTRICT"

    assert _column_names(orm_engine, "llm_calls") == _column_names(migrated_engine, "llm_calls")
    assert _column_names(orm_engine, "agent_actions") == _column_names(
        migrated_engine,
        "agent_actions",
    )

    backend_dir = Path(__file__).resolve().parents[2]
    migration_text = (backend_dir / "migrations/versions/0030_llm_action.py").read_text(
        encoding="utf-8"
    )
    for expected_fragment in (
        'revision = "0030_llm_action"',
        'down_revision = "0020_task_domain"',
        "parse_status_values",
        "action_sequence_positive",
    ):
        assert expected_fragment in migration_text


def _create_schema(database_path: Path) -> Engine:
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    return engine


def _create_migrated_schema(database_path: Path) -> Engine:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    config.set_main_option("prepend_sys_path", str(backend_dir / "src"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return create_sqlite_engine(f"sqlite:///{database_path}")


def _insert_iteration(session_factory: Any, tmp_path: Path) -> tuple[str, str]:
    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Persist LLM and AgentAction observability.",
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        iteration = TaskIteration(
            task_id=task.id,
            iteration_number=1,
            phase=TaskIterationPhase.ANALYZE,
        )
        session.add(iteration)
        session.flush()
        return task.id, iteration.id


def _insert_llm_call(session_factory: Any, iteration_id: str) -> str:
    with session_scope(session_factory) as session:
        call = LLMCall(
            iteration_id=iteration_id,
            provider_name="openai",
            model_name="gpt-5",
            input_tokens=10,
            output_tokens=5,
            status=LLMCallStatus.SUCCESS,
            parse_status=ParseStatus.VALID,
        )
        session.add(call)
        session.flush()
        return call.id


def _execute(engine: Engine, statement: str, parameters: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement), parameters)


def _column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


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


def _foreign_key_ondelete(engine: Engine, table_name: str, constrained_column: str) -> str:
    for foreign_key in inspect(engine).get_foreign_keys(table_name):
        if foreign_key["constrained_columns"] == [constrained_column]:
            return str(foreign_key["options"].get("ondelete"))
    raise AssertionError(f"missing foreign key for {table_name}.{constrained_column}")


def _sqlite_dump(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        return "\n".join(connection.iterdump())
