from __future__ import annotations

from fastapi.testclient import TestClient

from se_mentor.main import create_app


def test_T095_governance_exposes_facts_inference_unknowns_and_three_decisions() -> None:
    client = TestClient(create_app())
    project = client.post("/api/projects", json={"rootPath": "C:/repo"}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change auth"},
    ).json()["data"]
    proposal = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={"goal": "change auth"},
    ).json()["data"]
    client.post(f"/api/tasks/{task['id']}/proposals/{proposal['id']}/confirm")

    allow = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": ["src/user.py"]},
    )
    warn = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": ["auth/middleware.py"]},
    )
    block = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": [".env"]},
    )

    assert allow.json()["data"]["decision"] == "ALLOW"
    assert warn.json()["data"]["decision"] == "WARN"
    assert warn.json()["data"]["facts"]
    assert warn.json()["data"]["inferences"]
    assert warn.json()["data"]["unknowns"]
    assert warn.json()["data"]["evidence"]
    assert warn.json()["data"]["impactScope"]["summary"] == "1 个文件受影响"
    assert warn.json()["data"]["ruleHits"][0]["level"] == "WARN"
    assert block.json()["data"]["decision"] == "BLOCK"
    assert block.json()["data"]["nonApprovable"] is True
