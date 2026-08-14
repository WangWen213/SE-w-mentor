from __future__ import annotations

import importlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_mentor.models.evaluation import TaskEvaluation
from se_mentor.models.governance import GovernanceDecision, ImpactReport
from se_mentor.models.knowledge import EngineeringKnowledge
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalCreatedByType
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.runtime.online_sessions import ONLINE_SESSION_COOKIE_NAME


def test_online_safe_domain_state_is_isolated_by_project_owner_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api, events_api = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    client_a = TestClient(app_module.create_app(), base_url="https://testserver")
    client_b = TestClient(app_module.create_app(), base_url="https://testserver")

    project_a = _import_project(client_a, {"app.py": "print('a')\n"})
    project_b = _import_project(client_b, {"app.py": "print('b')\n"})
    session_a = client_a.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    session_b = client_b.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    seeded = _seed_domain_state(runtime_module, project_a["id"], project_b["id"])
    events_api.BUS.publish(
        task_id=seeded["task_a"],
        event_type="progress",
        payload={"message": "A only"},
    )

    list_a = client_a.get("/api/projects")
    list_b = client_b.get("/api/projects")
    b_get_a_project = client_b.get(f"/api/projects/{project_a['id']}")
    b_get_a_task = client_b.get(f"/api/tasks/{seeded['task_a']}")
    b_get_a_proposal = client_b.get(f"/api/tasks/{seeded['task_a']}/proposals")
    b_confirm_a_proposal = client_b.post(
        f"/api/tasks/{seeded['task_a']}/proposals/{seeded['proposal_a']}/confirm"
    )
    b_governance_a = client_b.get(f"/api/proposals/{seeded['proposal_a']}/governance")
    b_evaluation_a = client_b.get(f"/api/tasks/{seeded['task_a']}/evaluation")
    b_memory_a = client_b.get(f"/api/projects/{project_a['id']}/knowledge")
    b_sse_a = client_b.get(f"/api/tasks/{seeded['task_a']}/events")
    b_execution_a = client_b.post(
        f"/api/tasks/{seeded['task_a']}/execute",
        json={"command": "pytest"},
    )
    a_get_own_task = client_a.get(f"/api/tasks/{seeded['task_a']}")
    a_get_own_memory = client_a.get(f"/api/projects/{project_a['id']}/knowledge")
    a_get_own_sse = client_a.get(f"/api/tasks/{seeded['task_a']}/events")
    db_bytes = b"".join(path.read_bytes() for path in (tmp_path / "runtime").glob("*.sqlite3*"))

    assert project_a["id"] != project_b["id"]
    assert project_a["rootPath"] == "Uploaded Project"
    assert str(tmp_path) not in str(project_a)
    assert session_a != session_b
    assert [item["id"] for item in list_a.json()["data"]["items"]] == [project_a["id"]]
    assert [item["id"] for item in list_b.json()["data"]["items"]] == [project_b["id"]]
    assert b_get_a_project.status_code == 404
    assert b_get_a_task.status_code == 404
    assert b_get_a_proposal.status_code == 404
    assert b_confirm_a_proposal.status_code == 404
    assert b_governance_a.status_code == 404
    assert b_evaluation_a.status_code == 404
    assert b_memory_a.status_code == 404
    assert b_sse_a.status_code == 404
    assert b_execution_a.status_code == 404
    assert a_get_own_task.status_code == 200
    assert a_get_own_memory.status_code == 200
    assert a_get_own_memory.json()["data"]["items"][0]["summary"] == "A memory"
    assert a_get_own_sse.status_code == 200
    assert "A only" in a_get_own_sse.text
    assert session_a.encode("utf-8") not in db_bytes
    assert session_b.encode("utf-8") not in db_bytes


def test_online_safe_rejects_user_root_and_reuses_current_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api, _ = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")

    rejected = client.post("/api/projects", json={"rootPath": "/root"})
    created = _import_project_response(client, {"app.py": "print('own')\n"})
    reopened = _import_project_response(client, {"other.py": "print('ignored')\n"})
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)

    with runtime_module.get_session_factory()() as session:
        projects = session.query(Project).all()

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ONLINE_SAFE_USER_PATH_NOT_ALLOWED"
    assert created.status_code == 201
    assert reopened.status_code == 200
    assert reopened.json()["data"]["id"] == created.json()["data"]["id"]
    assert session_id not in str(created.json())
    assert all(project.owner_session_hash is not None for project in projects)


def _seed_domain_state(runtime_module, project_a: str, project_b: str) -> dict[str, str]:
    with runtime_module.get_session_factory()() as session:
        task_a = ChangeTask(project_id=project_a, original_request="A task")
        task_b = ChangeTask(project_id=project_b, original_request="B task")
        session.add_all([task_a, task_b])
        session.flush()
        proposal_a = ChangeProposal(
            task_id=task_a.id,
            version=1,
            goal="A goal",
            expected_behavior="A behavior",
            initial_scope_json=json.dumps(["app.py"]),
            acceptance_criteria_json=json.dumps([]),
            status="CONFIRMED",
            created_by_type=ProposalCreatedByType.USER,
        )
        session.add(proposal_a)
        session.flush()
        impact_a = ImpactReport(
            task_id=task_a.id,
            proposal_id=proposal_a.id,
            direct_impacts_json=json.dumps([]),
            evidence_json=json.dumps({}),
            status="CURRENT",
        )
        session.add(impact_a)
        session.flush()
        session.add(
            GovernanceDecision(
                task_id=task_a.id,
                impact_report_id=impact_a.id,
                proposal_hash="a" * 64,
                revision="baseline",
                decision="ALLOW",
                risk_level="LOW",
                reason_summary="Allowed.",
                approval_required=False,
                status="ACTIVE",
                rule_set_version="test",
                evidence_json=json.dumps({}),
            )
        )
        session.add(
            TaskEvaluation(
                project_id=project_a,
                task_id=task_a.id,
                status="COMPLETED",
                summary_json=json.dumps({"summary": "A evaluation"}),
            )
        )
        session.add(
            EngineeringKnowledge(
                project_id=project_a,
                knowledge_key="a-memory",
                knowledge_type="PATTERN",
                status="VERIFIED",
                version=1,
                scope_json=json.dumps([]),
                summary="A memory",
                verified_evidence_json=json.dumps([]),
            )
        )
        session.add(
            WorkbenchMessage(
                task_id=task_a.id,
                sequence=1,
                role="USER",
                kind="TEXT",
                status="DONE",
                text="A message",
            )
        )
        session.commit()
        return {"task_a": task_a.id, "task_b": task_b.id, "proposal_a": proposal_a.id}


def _import_project(client: TestClient, files: dict[str, str]) -> dict[str, object]:
    return _import_project_response(client, files).json()["data"]


def _import_project_response(client: TestClient, files: dict[str, str]):
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return client.post(
        "/api/projects/import-zip",
        content=output.getvalue(),
        headers={"content-type": "application/zip"},
    )


def _demo_workspace(tmp_path: Path) -> Path:
    demo_workspace = tmp_path / "demo-workspace"
    baseline = demo_workspace / ".baseline"
    baseline.mkdir(parents=True)
    (baseline / "README.md").write_text("baseline\n", encoding="utf-8")
    (baseline / "app.py").write_text("print('baseline')\n", encoding="utf-8")
    return demo_workspace


def _reload_api_for_online_safe(
    monkeypatch: pytest.MonkeyPatch,
    runtime_root: Path,
    demo_workspace: Path,
):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    monkeypatch.setenv("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("SE_MENTOR_DEMO_WORKSPACE", str(demo_workspace))
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.events as events_api
    import se_mentor.api.execution as execution_api
    import se_mentor.api.governance as governance_api
    import se_mentor.api.memory as memory_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.proposals as proposals_api
    import se_mentor.api.runtime as runtime
    import se_mentor.api.runtime_workspace as runtime_workspace_api
    import se_mentor.api.tasks as tasks_api
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    projects_api = importlib.reload(projects_api)
    credentials_api = importlib.reload(credentials_api)
    runtime_workspace_api = importlib.reload(runtime_workspace_api)
    importlib.reload(tasks_api)
    importlib.reload(proposals_api)
    importlib.reload(governance_api)
    importlib.reload(memory_api)
    execution_api = importlib.reload(execution_api)
    events_api = importlib.reload(events_api)
    main = importlib.reload(main)
    return main, runtime, projects_api, events_api
