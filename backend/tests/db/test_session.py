from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import exc, text

from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope


def test_transaction_rolls_back_and_foreign_key_is_enforced(tmp_path: Path) -> None:
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
