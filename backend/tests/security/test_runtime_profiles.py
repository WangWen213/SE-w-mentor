from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phase1_test_helpers import create_schema

from se_mentor.db.session import create_session_factory
from se_mentor.execution.orchestrator import ExecutionOrchestrator
from se_mentor.models.project import Project
from se_mentor.projects.project_service import register_project
from se_mentor.runtime.demo import reset_demo_runtime, reset_demo_workspace
from se_mentor.runtime.profiles import RuntimeProfile, RuntimeProfileError, get_runtime_profile


def test_local_full_is_default_and_invalid_profile_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("SE_MENTOR_RUNTIME_PROFILE", raising=False)
    assert get_runtime_profile() is RuntimeProfile.LOCAL_FULL

    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "CLOUD-DEMO")
    with pytest.raises(RuntimeProfileError):
        get_runtime_profile()


def test_local_full_project_registration_semantics_remain_unchanged(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    engine = create_schema(tmp_path / "local.sqlite3")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        registered = register_project(session, repo, authorized_root=repo)
        assert registered.project.root_path == str(repo)
        with pytest.raises(Exception, match="outside authorized root"):
            register_project(session, repo, authorized_root=outside)


def test_cloud_demo_accepts_only_predefined_workspace(monkeypatch, tmp_path: Path) -> None:
    demo_root = _demo_workspace(tmp_path)
    runtime_root = tmp_path / "demo-runtime"
    app_module, projects_api, _, _, _ = _reload_api_for_cloud_demo(
        monkeypatch, demo_root, runtime_root
    )
    client = TestClient(app_module.create_app())

    accepted = client.post("/api/projects", json={"rootPath": str(demo_root)})
    rejected = client.post("/api/projects", json={"rootPath": str(tmp_path)})
    traversal = client.post(
        "/api/projects",
        json={"rootPath": str((demo_root / ".." / tmp_path.name).resolve())},
    )
    picker = client.post("/api/projects/choose-local")

    assert accepted.status_code == 201
    assert accepted.json()["data"]["rootPath"] == str(demo_root)
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "CLOUD_DEMO_PROJECT_RESTRICTED"
    assert traversal.status_code == 400
    assert picker.status_code == 409
    assert projects_api.get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO


def test_cloud_demo_forces_mock_provider_and_ignores_credentials(
    monkeypatch, tmp_path: Path
) -> None:
    demo_root = _demo_workspace(tmp_path)
    runtime_root = tmp_path / "demo-runtime"
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder-openai-key-not-used")
    app_module, _, credentials_api, runtime_module, _ = _reload_api_for_cloud_demo(
        monkeypatch, demo_root, runtime_root
    )
    touched = False

    class FailingStore:
        def status(self):
            nonlocal touched
            touched = True
            raise AssertionError("credential store must not be read in CLOUD_DEMO")

    monkeypatch.setattr(runtime_module, "_CREDENTIAL_STORE", FailingStore())
    provider = runtime_module.get_domain_provider()
    status_response = TestClient(app_module.create_app()).get("/api/credentials/llm/status")
    set_response = TestClient(app_module.create_app()).post(
        "/api/credentials/llm",
        json={
            "provider": "OpenAI",
            "key": "placeholder-openai-key-not-used",
            "baseUrl": "https://api.example.test/v1",
            "model": "real-model",
        },
    )

    assert provider.provider_name == "mock"
    assert status_response.status_code == 200
    assert status_response.json()["data"]["provider"] == "Mock"
    assert set_response.status_code == 409
    assert set_response.json()["error"]["code"] == "CLOUD_DEMO_CREDENTIALS_DISABLED"
    assert touched is False
    assert credentials_api.get_runtime_settings().profile is RuntimeProfile.CLOUD_DEMO


def test_cloud_demo_tool_registry_excludes_run_command(monkeypatch, tmp_path: Path) -> None:
    demo_root = _demo_workspace(tmp_path)
    runtime_root = tmp_path / "demo-runtime"
    _, _, _, _, orchestrator_module = _reload_api_for_cloud_demo(
        monkeypatch, demo_root, runtime_root
    )
    engine = create_schema(tmp_path / "tools.sqlite3")
    session_factory = create_session_factory(engine)
    captured = {}

    class CaptureRuntime:
        def __init__(self, session, *, runner, policy=None) -> None:
            captured["tools"] = {item.name for item in runner.registry.list_specs()}

    monkeypatch.setattr(orchestrator_module, "AgentRuntime", CaptureRuntime)
    with session_factory() as session:
        project = Project(root_path=str(demo_root))
        session.add(project)
        session.flush()
        task = type("Task", (), {"project": project})()
        orchestrator_module.ExecutionOrchestrator(session_factory)._runtime_for(
            session,
            task,
            authorization=_Authorization(),
            write_context=object(),
        )

    assert "RUN_COMMAND" not in captured["tools"]
    assert {"READ_FILE", "SEARCH_CODE", "APPLY_PATCH"}.issubset(captured["tools"])


def test_demo_reset_is_idempotent_and_does_not_touch_local_storage(tmp_path: Path) -> None:
    demo_root = _demo_workspace(tmp_path)
    runtime_root = tmp_path / "demo-runtime"
    local_root = tmp_path / "local-runtime"
    local_db = local_root / "se_mentor_api.sqlite3"
    local_root.mkdir()
    local_db.write_text("keep me", encoding="utf-8")

    (demo_root / "app.py").write_text("modified\n", encoding="utf-8")
    (runtime_root / "se_mentor_api.sqlite3").parent.mkdir(parents=True)
    (runtime_root / "se_mentor_api.sqlite3").write_text("demo state", encoding="utf-8")

    reset_demo_runtime(runtime_root, demo_workspace_root=demo_root)
    reset_demo_runtime(runtime_root, demo_workspace_root=demo_root)

    assert (demo_root / "app.py").read_text(encoding="utf-8") == (
        demo_root / ".baseline" / "app.py"
    ).read_text(encoding="utf-8")
    assert not (runtime_root / "se_mentor_api.sqlite3").exists()
    assert local_db.read_text(encoding="utf-8") == "keep me"


def _reload_api_for_cloud_demo(monkeypatch, demo_root: Path, runtime_root: Path):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "CLOUD_DEMO")
    monkeypatch.setenv("SE_MENTOR_DEMO_WORKSPACE", str(demo_root))
    monkeypatch.setenv("SE_MENTOR_DEMO_RUNTIME_ROOT", str(runtime_root))
    import se_mentor.api.runtime as runtime
    import se_mentor.api.projects as projects_api
    import se_mentor.api.credentials as credentials_api
    import se_mentor.execution.orchestrator as orchestrator_module
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    projects_api = importlib.reload(projects_api)
    credentials_api = importlib.reload(credentials_api)
    orchestrator_module = importlib.reload(orchestrator_module)
    main = importlib.reload(main)
    return main, projects_api, credentials_api, runtime, orchestrator_module


def _demo_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "demo-workspace"
    baseline = root / ".baseline"
    baseline.mkdir(parents=True)
    (baseline / "README.md").write_text("demo\n", encoding="utf-8")
    (baseline / "app.py").write_text("def greeting():\n    return 'hello'\n", encoding="utf-8")
    reset_demo_workspace(root)
    return root


def _git_repo(root: Path) -> Path:
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


class _Authorization:
    revision = "rev-1"
