from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.config.loader import EffectiveConfig, freeze_task_config


@dataclass(frozen=True)
class DatabaseRuntimeSettings:
    database_url: str
    sqlite_busy_timeout_ms: int
    config_version: int
    config_hash: str


def database_settings_from_effective_config(
    effective_config: EffectiveConfig,
    *,
    database_url: str,
    sqlite_busy_timeout_ms: int = 5000,
) -> DatabaseRuntimeSettings:
    if sqlite_busy_timeout_ms <= 0:
        raise ValueError("sqlite_busy_timeout_ms must be positive")
    frozen_config = freeze_task_config("database-runtime", effective_config)
    return DatabaseRuntimeSettings(
        database_url=database_url,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        config_version=effective_config.version,
        config_hash=frozen_config.config_hash,
    )


def create_sqlite_engine(
    database_url: str,
    *,
    echo: bool = False,
    sqlite_busy_timeout_ms: int = 5000,
) -> Engine:
    if sqlite_busy_timeout_ms <= 0:
        raise ValueError("sqlite_busy_timeout_ms must be positive")
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        event.listen(
            engine,
            "connect",
            lambda connection, record: _configure_sqlite_connection(
                connection,
                record,
                busy_timeout_ms=sqlite_busy_timeout_ms,
            ),
        )

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _configure_sqlite_connection(
    dbapi_connection: Any,
    _connection_record: Any,
    *,
    busy_timeout_ms: int,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    finally:
        cursor.close()
