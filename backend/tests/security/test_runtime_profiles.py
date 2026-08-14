from __future__ import annotations

import importlib
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from phase1_test_helpers import create_schema

from se_mentor.db.session import create_session_factory
from se_mentor.models.project import Project
from se_mentor.projects.project_service import register_project
from se_mentor.runtime.demo import reset_demo_runtime, reset_demo_workspace
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    ONLINE_SESSION_TTL_SECONDS,
    InMemoryOnlineSessionStore,
)
from se_mentor.runtime.profiles import RuntimeProfile, RuntimeProfileError, get_runtime_profile

ONLINE_SAFE_TEST_KEY = "test-online-safe-secret-value"


def test_local_full_is_default_and_invalid_profile_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("SE_MENTOR_RUNTIME_PROFILE", raising=False)
    assert get_runtime_profile() is RuntimeProfile.LOCAL_FULL

    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    assert get_runtime_profile() is RuntimeProfile.ONLINE_SAFE

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


def test_online_safe_credentials_use_secure_ephemeral_session_store(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    app_module, projects_api, credentials_api, runtime_module, _ = _reload_api_for_online_safe(
        monkeypatch, runtime_root
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _online_resolver({"api.example.test": ["93.184.216.34"]}),
    )

    class FailingStore:
        def status(self):
            raise AssertionError("ONLINE_SAFE must not read global credentials")

        def set_api_key(self, value):
            raise AssertionError("ONLINE_SAFE must not write global credentials")

        def update_api_key(self, value):
            raise AssertionError("ONLINE_SAFE must not update global credentials")

        def clear_api_key(self):
            raise AssertionError("ONLINE_SAFE must not clear global credentials")

    monkeypatch.setattr(runtime_module, "_CREDENTIAL_STORE", FailingStore())
    http_client = TestClient(app_module.create_app())
    https_client = TestClient(app_module.create_app(), base_url="https://testserver")

    status_response = https_client.get("/api/credentials/llm/status")
    cookie_header = status_response.headers["set-cookie"]
    initial_session_id = https_client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    http_post_response = http_client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
        headers={"X-Forwarded-Proto": "https"},
    )
    post_response = https_client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    session_after_post = https_client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    after_set_response = https_client.get("/api/credentials/llm/status")
    session_after_refresh = https_client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    refresh_cookie_header = after_set_response.headers["set-cookie"]
    put_response = https_client.put(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": "",
            "baseUrl": "https://api.example.test/v2",
            "model": "model-b",
        },
    )
    delete_response = https_client.delete("/api/credentials/llm")
    after_delete_response = https_client.get("/api/credentials/llm/status")
    session_id = https_client.cookies.get(ONLINE_SESSION_COOKIE_NAME)

    assert status_response.status_code == 200
    assert status_response.json()["data"]["configured"] is False
    assert ONLINE_SESSION_COOKIE_NAME in cookie_header
    assert "Max-Age=43200" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Secure" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert http_post_response.status_code == 409
    assert http_post_response.json()["error"]["code"] == runtime_module.ONLINE_SAFE_HTTPS_ERROR
    assert post_response.status_code == 200
    assert post_response.json()["data"]["configured"] is True
    assert after_set_response.status_code == 200
    assert after_set_response.json()["data"]["configured"] is True
    assert initial_session_id == session_after_post == session_after_refresh
    assert "Max-Age=43200" in refresh_cookie_header
    assert after_set_response.json()["data"]["source"] == "ONLINE_SAFE_SESSION"
    assert "key" not in str(after_set_response.json()).lower()
    assert ONLINE_SAFE_TEST_KEY not in str(after_set_response.json())
    assert put_response.status_code == 200
    assert put_response.json()["data"]["baseUrl"] == "https://api.example.test/v2"
    assert put_response.json()["data"]["model"] == "model-b"
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["configured"] is False
    assert after_delete_response.json()["data"]["configured"] is False
    assert runtime_module.get_online_session_store().credential_for(session_id) is None
    assert projects_api.get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE
    assert credentials_api.get_runtime_settings().profile is RuntimeProfile.ONLINE_SAFE


def test_online_safe_trusted_proxy_accepts_gateway_forwarded_https(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    app_module, _, credentials_api, runtime_module, _ = _reload_api_for_online_safe(
        monkeypatch,
        runtime_root,
        trust_proxy=True,
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _online_resolver({"api.example.test": ["93.184.216.34"]}),
    )
    client = TestClient(app_module.create_app())

    status_response = client.get("/api/credentials/llm/status")
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    set_response = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
        headers={
            "Cookie": f"{ONLINE_SESSION_COOKIE_NAME}={session_id}",
            "X-Forwarded-Proto": "https",
        },
    )

    assert status_response.status_code == 200
    assert credentials_api.get_runtime_settings().trust_proxy is True
    assert runtime_module.get_runtime_settings().trust_proxy is True
    assert set_response.status_code == 200
    assert set_response.json()["data"]["configured"] is True


def test_online_safe_session_ttl_is_12h_sliding_and_cookie_refreshes(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    current_time = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, runtime_root)
    store = InMemoryOnlineSessionStore(
        ttl_seconds=ONLINE_SESSION_TTL_SECONDS,
        max_active_sessions=8,
        clock=lambda: current_time,
    )
    monkeypatch.setattr(runtime_module, "_ONLINE_SESSION_STORE", store)
    client = TestClient(app_module.create_app(), base_url="https://testserver")

    first = client.get("/api/credentials/llm/status")
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    session = store.require(session_id)

    assert ONLINE_SESSION_TTL_SECONDS == 43200
    assert first.status_code == 200
    assert "Max-Age=43200" in first.headers["set-cookie"]
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "Secure" in first.headers["set-cookie"]
    assert "SameSite=lax" in first.headers["set-cookie"]
    assert session.expires_at == current_time + timedelta(hours=12)

    current_time += timedelta(hours=11)
    refresh = client.get("/api/credentials/llm/status")
    refreshed = store.require(session_id)

    assert client.cookies.get(ONLINE_SESSION_COOKIE_NAME) == session_id
    assert "Max-Age=43200" in refresh.headers["set-cookie"]
    assert refreshed.expires_at == datetime(2026, 8, 14, 23, 0, tzinfo=UTC)


def test_online_safe_session_credentials_are_isolated_and_expire(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    current_time = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, runtime_root)
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _online_resolver(
            {
                "a.example.test": ["93.184.216.34"],
                "b.example.test": ["93.184.216.35"],
            }
        ),
    )
    store = InMemoryOnlineSessionStore(
        ttl_seconds=60,
        max_active_sessions=8,
        clock=lambda: current_time,
    )
    monkeypatch.setattr(runtime_module, "_ONLINE_SESSION_STORE", store)
    client_a = TestClient(app_module.create_app(), base_url="https://testserver")
    client_b = TestClient(app_module.create_app(), base_url="https://testserver")

    client_a.get("/api/credentials/llm/status")
    client_b.get("/api/credentials/llm/status")
    client_a.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": f"{ONLINE_SAFE_TEST_KEY}-a",
            "baseUrl": "https://a.example.test/v1",
            "model": "model-a",
        },
    )
    client_b.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": f"{ONLINE_SAFE_TEST_KEY}-b",
            "baseUrl": "https://b.example.test/v1",
            "model": "model-b",
        },
    )

    session_a = client_a.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    session_b = client_b.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    credential_a = store.credential_for(session_a)
    credential_b = store.credential_for(session_b)

    assert credential_a is not None
    assert credential_b is not None
    assert credential_a.secret.reveal() == f"{ONLINE_SAFE_TEST_KEY}-a"
    assert credential_b.secret.reveal() == f"{ONLINE_SAFE_TEST_KEY}-b"
    assert credential_a.secret.reveal() != credential_b.secret.reveal()
    assert client_a.get("/api/credentials/llm/status").json()["data"]["baseUrl"] == (
        "https://a.example.test/v1"
    )
    assert client_b.get("/api/credentials/llm/status").json()["data"]["baseUrl"] == (
        "https://b.example.test/v1"
    )

    current_time += timedelta(seconds=61)
    expired_response = client_a.get("/api/credentials/llm/status")

    assert expired_response.status_code == 200
    assert expired_response.json()["data"]["configured"] is False
    assert store.credential_for(session_a) is None


def test_online_safe_store_reset_loses_credentials_and_sqlite_never_contains_key(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, runtime_root)
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _online_resolver({"api.example.test": ["93.184.216.34"]}),
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")

    client.get("/api/credentials/llm/status")
    set_response = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    sqlite_files = list(runtime_root.glob("se_mentor_api.sqlite3*"))

    assert set_response.status_code == 200
    assert runtime_module.get_online_session_store().credential_for(session_id) is not None
    assert sqlite_files
    assert all(ONLINE_SAFE_TEST_KEY.encode() not in path.read_bytes() for path in sqlite_files)

    runtime_module.get_online_session_store().reset()
    reset_response = client.get("/api/credentials/llm/status")

    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["configured"] is False
    assert runtime_module.get_online_session_store().credential_for(session_id) is None


def test_online_safe_provider_is_locked_without_env_key_or_mock_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder-openai-key-not-used")
    monkeypatch.setenv("SE_MENTOR_LLM_PROFILE", "MOCK")
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, runtime_root)

    class FailingStore:
        def provider(self):
            raise AssertionError("ONLINE_SAFE must not read global credentials")

        def provider_metadata(self):
            raise AssertionError("ONLINE_SAFE must not read provider metadata")

    monkeypatch.setattr(runtime_module, "_CREDENTIAL_STORE", FailingStore())

    with pytest.raises(runtime_module.OnlineSafeNotReadyError) as exc:
        runtime_module.get_domain_provider()

    status_response = TestClient(
        app_module.create_app(),
        base_url="https://testserver",
    ).get("/api/credentials/llm/status")

    assert str(exc.value) == runtime_module.ONLINE_SAFE_PROVIDER_ERROR
    assert status_response.status_code == 200
    assert status_response.json()["data"]["configured"] is False


def test_online_safe_project_registration_is_locked(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, runtime_root)
    client = TestClient(app_module.create_app(), base_url="https://testserver")

    source_repo = Path.cwd()
    root_response = client.post("/api/projects", json={"rootPath": "/root"})
    etc_response = client.post("/api/projects", json={"rootPath": "/etc"})
    source_response = client.post("/api/projects", json={"rootPath": str(source_repo)})
    create_current_response = client.post("/api/projects", json={})
    picker_response = client.post("/api/projects/choose-local")

    assert root_response.status_code == 409
    assert root_response.json()["error"]["code"] == "ONLINE_SAFE_USER_PATH_NOT_ALLOWED"
    assert etc_response.status_code == 409
    assert etc_response.json()["error"]["code"] == "ONLINE_SAFE_USER_PATH_NOT_ALLOWED"
    assert source_response.status_code == 409
    assert source_response.json()["error"]["code"] == "ONLINE_SAFE_USER_PATH_NOT_ALLOWED"
    assert create_current_response.status_code == 409
    assert create_current_response.json()["error"]["code"] == "ONLINE_SAFE_PROJECT_ZIP_REQUIRED"
    assert picker_response.status_code == 409
    assert picker_response.json()["error"]["code"] == "ONLINE_SAFE_PROJECT_ZIP_REQUIRED"
    assert str(runtime_root) not in str(create_current_response.json())


def test_online_safe_tool_registry_excludes_run_command(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "online-safe-runtime"
    _, _, _, _, orchestrator_module = _reload_api_for_online_safe(monkeypatch, runtime_root)
    engine = create_schema(tmp_path / "tools.sqlite3")
    session_factory = create_session_factory(engine)
    captured = {}

    class CaptureRuntime:
        def __init__(self, session, *, runner, policy=None) -> None:
            captured["tools"] = {item.name for item in runner.registry.list_specs()}

    monkeypatch.setattr(orchestrator_module, "AgentRuntime", CaptureRuntime)
    with session_factory() as session:
        project = Project(root_path=str(tmp_path))
        session.add(project)
        session.flush()
        task = type("Task", (), {"project": project})()
        orchestrator_module.ExecutionOrchestrator(
            session_factory, provider_override=object()
        )._runtime_for(
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
    monkeypatch.delenv("SE_MENTOR_TRUST_PROXY", raising=False)
    monkeypatch.setenv("SE_MENTOR_DEMO_WORKSPACE", str(demo_root))
    monkeypatch.setenv("SE_MENTOR_DEMO_RUNTIME_ROOT", str(runtime_root))
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.runtime as runtime
    import se_mentor.execution.orchestrator as orchestrator_module
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    projects_api = importlib.reload(projects_api)
    credentials_api = importlib.reload(credentials_api)
    orchestrator_module = importlib.reload(orchestrator_module)
    main = importlib.reload(main)
    return main, projects_api, credentials_api, runtime, orchestrator_module


def _reload_api_for_online_safe(
    monkeypatch,
    runtime_root: Path,
    *,
    trust_proxy: bool = False,
):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    monkeypatch.setenv("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    if trust_proxy:
        monkeypatch.setenv("SE_MENTOR_TRUST_PROXY", "true")
    else:
        monkeypatch.delenv("SE_MENTOR_TRUST_PROXY", raising=False)
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.online_readiness as online_readiness_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.runtime as runtime
    import se_mentor.execution.orchestrator as orchestrator_module
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    importlib.reload(online_readiness_api)
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


def _online_resolver(hosts: dict[str, list[str]]):
    def resolve(host: str, port: int | None, *args: object):
        addresses = hosts[host.lower().rstrip(".")]
        return [
            (
                0,
                0,
                0,
                "",
                (address, port or 443),
            )
            for address in addresses
        ]

    return resolve
