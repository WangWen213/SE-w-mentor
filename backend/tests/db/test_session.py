from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import exc, text

from se_mentor.config.loader import merge_config
from se_mentor.config.profiles import ProfileName, profile_layer
from se_mentor.db.session import (
    create_session_factory,
    create_sqlite_engine,
    database_settings_from_effective_config,
    session_scope,
)


def test_T007_transaction_rolls_back_and_foreign_key_is_enforced(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    session_factory = create_session_factory(engine)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
        connection.execute(text("CREATE TABLE parents (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE children ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parents(id)"
                ")"
            )
        )

    with pytest.raises(RuntimeError), session_scope(session_factory) as session:
        session.execute(text("INSERT INTO items (name) VALUES ('rolled-back')"))
        raise RuntimeError("force rollback")

    with session_scope(session_factory) as session:
        count = session.execute(text("SELECT COUNT(*) FROM items")).scalar_one()

    assert count == 0

    with pytest.raises(exc.IntegrityError), session_scope(session_factory) as session:
        session.execute(text("INSERT INTO children (parent_id) VALUES (404)"))


def test_T007_sqlite_connection_enables_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = create_sqlite_engine(
        f"sqlite:///{tmp_path / 'pragma.sqlite3'}",
        sqlite_busy_timeout_ms=7000,
    )

    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert busy_timeout == 7000


def test_T007_database_settings_are_supplied_by_effective_config(tmp_path: Path) -> None:
    effective = merge_config(profile_layer(ProfileName.LOCAL_FULL))

    settings = database_settings_from_effective_config(
        effective,
        database_url=f"sqlite:///{tmp_path / 'configured.sqlite3'}",
        sqlite_busy_timeout_ms=9000,
    )
    engine = create_sqlite_engine(
        settings.database_url,
        sqlite_busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )

    with engine.connect() as connection:
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert settings.config_version == effective.version
    assert settings.config_hash
    assert busy_timeout == 9000


def test_T007_alembic_uses_explicit_database_url_without_env(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "alembic-explicit.sqlite3"
    database_url = f"sqlite:///{database_path}"
    env = os.environ.copy()
    env.pop("SE_MENTOR_DATABASE_URL", None)
    env["TMP"] = str(tmp_path)
    env["TEMP"] = str(tmp_path)

    upgrade = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "-x",
            f"database_url={database_url}",
            "upgrade",
            "head",
        ],
        cwd=backend_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    downgrade = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "-x",
            f"database_url={database_url}",
            "downgrade",
            "base",
        ],
        cwd=backend_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert upgrade.returncode == 0, upgrade.stderr
    assert database_path.exists()
    assert downgrade.returncode == 0, downgrade.stderr
