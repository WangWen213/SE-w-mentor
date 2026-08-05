from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_health_endpoint_returns_ok() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
