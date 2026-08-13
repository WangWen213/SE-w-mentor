from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from phase1_test_helpers import create_schema

from se_mentor.api import recovery
from se_mentor.db.session import create_session_factory
from se_mentor.main import create_app


def test_recovery_list_uses_cheap_empty_fast_path(monkeypatch, tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "recovery-fast-path.sqlite3")
    session_factory = create_session_factory(engine)
    recovery._SESSION_FACTORY = session_factory

    def fail_scan(*args, **kwargs):
        raise AssertionError("RecoveryService scan should not run without unfinished transactions")

    monkeypatch.setattr(recovery.TransactionRecoveryService, "scan_project", fail_scan)

    client = TestClient(create_app())
    response = client.get("/api/recovery")

    assert response.status_code == 200
    assert response.json()["data"] == {"items": []}
