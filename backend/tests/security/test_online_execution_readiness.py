from __future__ import annotations

import importlib
import json
import socket
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.projects.bootstrap import ProjectBootstrapService

ONLINE_SAFE_TEST_KEY = "test-online-safe-secret-value"


def test_online_safe_proposal_flow_is_not_blocked_by_phase4_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api, proposals_api, _ = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver({"api.example.test": ["93.184.216.34"]}),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    monkeypatch.setattr(proposals_api, "is_project_context_ready", lambda project_id: True)
    provider = MockLLMProvider(
        model="online-test",
        script=(
            MockResponse(
                match="structured change proposal",
                content=json.dumps(
                    {
                        "goal": "Update title",
                        "understanding": "The uploaded project title should change.",
                        "expected_behavior": "The title is updated.",
                        "scope": ["app.py"],
                        "changes": [
                            {
                                "path": "app.py",
                                "symbol": None,
                                "action": "Update title text",
                                "reason": "app.py contains the fixture title",
                            }
                        ],
                        "steps": ["Read app.py", "Patch the title"],
                        "non_goals": [],
                        "constraints": ["Do not run shell commands"],
                        "acceptance": ["app.py contains the new title"],
                        "validation": ["Inspect app.py"],
                        "user_facts": ["User requested a title change"],
                        "inferences": ["Single file fixture update"],
                        "risks": [],
                    }
                ),
                input_tokens=10,
                output_tokens=10,
            ),
            MockResponse(
                match="Bounded technical supplement",
                content=json.dumps(
                    {
                        "goal": "Update title",
                        "understanding": "The uploaded project title should change.",
                        "expected_behavior": "The title is updated.",
                        "scope": ["app.py"],
                        "changes": [
                            {
                                "path": "app.py",
                                "symbol": None,
                                "action": "Update title text",
                                "reason": "app.py contains the fixture title",
                            }
                        ],
                        "steps": ["Read app.py", "Patch the title"],
                        "non_goals": [],
                        "constraints": ["Do not run shell commands"],
                        "acceptance": ["app.py contains the new title"],
                        "validation": ["Inspect app.py"],
                        "user_facts": ["User requested a title change"],
                        "inferences": ["Single file fixture update"],
                        "risks": [],
                    }
                ),
                input_tokens=10,
                output_tokens=10,
            ),
        ),
    )
    monkeypatch.setattr(proposals_api, "_provider_for_project", lambda *args: provider)
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    project_id = _import_project(client, {"app.py": "TITLE = 'Old'\n"})["id"]
    _configure_credential(client)
    with runtime_module.get_session_factory()() as session:
        ProjectBootstrapService(session).bootstrap(project_id)
    task = client.post(
        "/api/tasks",
        json={"projectId": project_id, "request": "change title"},
    ).json()["data"]

    proposal = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={"goal": "change title"},
    )

    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["error"] is None
    assert proposal.json()["data"]["scope"] == ["app.py"]


def test_online_safe_execution_reaches_harness_boundary_with_session_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, _, projects_api, _, execution_api = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver({"api.example.test": ["93.184.216.34"]}),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    captured: dict[str, object] = {}

    class HarnessBoundary:
        def __init__(self, session_factory, *, runtime=None, provider_override=None) -> None:
            captured["provider"] = provider_override

        def execute_task(self, task_id: str, *, command: str):
            captured["command"] = command

            class Result:
                status = "COMPLETED"
                code = None
                error = None

                def payload(self):
                    return {"taskId": task_id, "status": "COMPLETED", "eventId": 1}

            return Result()

    monkeypatch.setattr(execution_api, "ExecutionOrchestrator", HarnessBoundary)
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    project_id = _import_project(client, {"app.py": "print('online')\n"})["id"]
    _configure_credential(client)
    task = client.post(
        "/api/tasks",
        json={"projectId": project_id, "request": "change title"},
    ).json()["data"]

    executed = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"command": "APPLY_APPROVED_CHANGES"},
    )

    assert executed.status_code == 200
    assert captured["command"] == "APPLY_APPROVED_CHANGES"
    assert captured["provider"].provider_name == "openai"


def _configure_credential(client: TestClient) -> None:
    response = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    assert response.status_code == 200


def _import_project(client: TestClient, files: dict[str, str]) -> dict[str, object]:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    response = client.post(
        "/api/projects/import-zip",
        content=output.getvalue(),
        headers={"content-type": "application/zip"},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _demo_workspace(tmp_path: Path) -> Path:
    demo_workspace = tmp_path / "demo-workspace"
    baseline = demo_workspace / ".baseline"
    baseline.mkdir(parents=True)
    (baseline / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=baseline, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "SE Mentor Test"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=baseline, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    return demo_workspace


def _resolver(hosts: dict[str, list[str]]):
    def resolve(host: str, port: int | None, *args: object):
        addresses = hosts[host.lower().rstrip(".")]
        infos = []
        for address in addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr = (
                (address, port or 443, 0, 0)
                if family is socket.AF_INET6
                else (address, port or 443)
            )
            infos.append((family, socket.SOCK_STREAM, 0, "", sockaddr))
        return infos

    return resolve


def _reload_api_for_online_safe(
    monkeypatch: pytest.MonkeyPatch,
    runtime_root: Path,
    demo_workspace: Path,
):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    monkeypatch.setenv("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("SE_MENTOR_DEMO_WORKSPACE", str(demo_workspace))
    monkeypatch.delenv("SE_MENTOR_TRUST_PROXY", raising=False)
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.execution as execution_api
    import se_mentor.api.online_readiness as online_readiness_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.proposals as proposals_api
    import se_mentor.api.runtime as runtime
    import se_mentor.api.tasks as tasks_api
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    importlib.reload(online_readiness_api)
    projects_api = importlib.reload(projects_api)
    importlib.reload(credentials_api)
    importlib.reload(tasks_api)
    proposals_api = importlib.reload(proposals_api)
    execution_api = importlib.reload(execution_api)
    main = importlib.reload(main)
    return main, runtime, projects_api, proposals_api, execution_api
