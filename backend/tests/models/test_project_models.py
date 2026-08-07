from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, exc, inspect, select

from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.models.project import (
    CredentialProfile,
    Project,
    ProjectConfig,
    normalize_project_root_path,
)


def test_T009_duplicate_project_path_and_plain_secret_are_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "project-domain.sqlite3"
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    project_root = tmp_path / "repo"
    equivalent_project_root = str(project_root) + "\\."

    with session_scope(session_factory) as session:
        session.add(Project(root_path=str(project_root)))

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(Project(root_path=equivalent_project_root))

    with pytest.raises(TypeError):
        CredentialProfile(
            project_id="project-id",
            provider="openai",
            keyring_reference="os-keyring:openai",
            configuration_status="configured",
            secret="fake-secret-T009",
        )

    columns = _column_names(engine, "credential_profiles")
    forbidden_columns = {"secret", "api_key", "token", "password", "credential_value"}
    assert columns.isdisjoint(forbidden_columns)
    assert "fake-secret-T009" not in _sqlite_dump(database_path)


def test_T009_project_round_trip_and_path_normalization(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'project-roundtrip.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    project_root = tmp_path / "repo" / ".." / "repo"

    with session_scope(session_factory) as session:
        project = Project(root_path=str(project_root))
        session.add(project)
        session.flush()
        project_id = project.id

    with session_scope(session_factory) as session:
        reloaded = session.get(Project, project_id)

    assert reloaded is not None
    assert reloaded.root_path == str(project_root)
    assert reloaded.normalized_root_path == normalize_project_root_path(project_root)


def test_T009_project_config_versions_round_trip_and_are_unique(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'project-config.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        session.add_all(
            [
                ProjectConfig(
                    project_id=project.id,
                    version=1,
                    effective_scope="project",
                    config_json='{"llm_provider":"mock"}',
                ),
                ProjectConfig(
                    project_id=project.id,
                    version=2,
                    effective_scope="project",
                    config_json='{"llm_provider":"openai"}',
                ),
            ]
        )
        project_id = project.id

    with session_scope(session_factory) as session:
        versions = session.scalars(
            select(ProjectConfig.version)
            .where(ProjectConfig.project_id == project_id)
            .order_by(ProjectConfig.version)
        ).all()

    assert versions == [1, 2]

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.add(
            ProjectConfig(
                project_id=project_id,
                version=2,
                effective_scope="project",
                config_json="{}",
            )
        )


def test_T009_credential_profile_round_trip_cascade_and_no_plaintext_sink(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "credential-profile.sqlite3"
    engine = create_sqlite_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        session.add(
            CredentialProfile(
                project_id=project.id,
                provider="openai",
                keyring_reference="os-keyring:se-mentor/openai/default",
                configuration_status="configured",
            )
        )
        project_id = project.id

    with session_scope(session_factory) as session:
        profile = session.scalars(
            select(CredentialProfile).where(CredentialProfile.project_id == project_id)
        ).one()

    assert profile.provider == "openai"
    assert profile.keyring_reference == "os-keyring:se-mentor/openai/default"
    assert profile.configuration_status == "configured"

    forbidden = ("fake-secret-T009", "api_key", "token", "password", "credential_value")
    table_names = inspect(engine).get_table_names()
    assert {"projects", "project_configs", "credential_profiles"}.issubset(table_names)
    backend_dir = Path(__file__).resolve().parents[2]
    migration_text = (backend_dir / "migrations/versions/0010_project_domain.py").read_text(
        encoding="utf-8"
    )
    dump = _sqlite_dump(database_path)

    for forbidden_fragment in forbidden:
        assert forbidden_fragment not in migration_text
        assert forbidden_fragment not in dump

    with session_scope(session_factory) as session:
        deleted_project = session.get(Project, project_id)
        assert deleted_project is not None
        session.delete(deleted_project)

    with session_scope(session_factory) as session:
        assert session.scalars(select(CredentialProfile)).all() == []


def _column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _sqlite_dump(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        return "\n".join(connection.iterdump())
