from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    InMemoryOnlineSessionStore,
)
from se_mentor.runtime.online_workspaces import (
    ONLINE_SAFE_USER_PATH_ERROR,
    ONLINE_SAFE_WORKSPACE_BASELINE_ERROR,
    ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR,
    ONLINE_SAFE_WORKSPACE_LIMIT_ERROR,
    ONLINE_SAFE_WORKSPACE_MAX_BYTES,
    ONLINE_SAFE_WORKSPACE_MAX_FILES,
    OnlineWorkspaceError,
    SafeOnlineWorkspaceFactory,
)

ONLINE_SAFE_TEST_KEY = "test-online-safe-secret-value"


def test_workspace_factory_creates_isolated_session_workspaces(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    factory = SafeOnlineWorkspaceFactory(
        runtime_root=tmp_path / "runtime",
        baseline_root=baseline,
    )
    store = InMemoryOnlineSessionStore(max_active_sessions=8)
    session_a = store.get_or_create(None)
    session_b = store.get_or_create(None)

    handle_a = factory.get_or_create(session_a)
    repeat_a = factory.get_or_create(session_a)
    handle_b = factory.get_or_create(session_b)
    (handle_a.root / "app.py").write_text("print('changed by a')\n", encoding="utf-8")
    (handle_b.root / "README.md").write_text("changed by b\n", encoding="utf-8")

    assert handle_a.root.is_dir()
    assert repeat_a.root == handle_a.root
    assert handle_a.root != handle_b.root
    assert (handle_b.root / "app.py").read_text(encoding="utf-8") == "print('baseline')\n"
    assert (baseline / "app.py").read_text(encoding="utf-8") == "print('baseline')\n"
    assert not (handle_a.root / ".env").exists()
    assert not (handle_a.root / "credentials.json").exists()
    assert not (handle_a.root / "__pycache__").exists()
    assert not (handle_a.root / ".git" / "config").read_text(encoding="utf-8").count("remote ")
    assert handle_a.root.is_relative_to(factory.sessions_root)
    assert not handle_a.root.samefile(baseline)
    assert handle_a.identifier != session_a.session_id

    reset_a = factory.reset_current_workspace(session_a)

    assert reset_a.root == handle_a.root
    assert (reset_a.root / "app.py").read_text(encoding="utf-8") == "print('baseline')\n"
    assert (handle_b.root / "README.md").read_text(encoding="utf-8") == "changed by b\n"


def test_workspace_cleanup_removes_expired_session_without_escape(tmp_path: Path) -> None:
    current_time = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
    baseline = _baseline(tmp_path)
    factory = SafeOnlineWorkspaceFactory(
        runtime_root=tmp_path / "runtime",
        baseline_root=baseline,
        clock=lambda: current_time,
    )
    store = InMemoryOnlineSessionStore(
        ttl_seconds=60,
        max_active_sessions=8,
        clock=lambda: current_time,
    )
    session = store.get_or_create(None)
    handle = factory.get_or_create(session)
    session_root = handle.root.parent

    current_time += timedelta(seconds=61)
    store.get_or_create(session.session_id)
    factory.cleanup_expired(store.active_session_ids())

    assert not session_root.exists()
    with pytest.raises(OnlineWorkspaceError) as exc:
        factory._safe_rmtree(tmp_path)
    assert exc.value.code == ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR


def test_workspace_path_resolution_blocks_host_paths_and_symlink_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    baseline = _baseline(tmp_path)
    factory = SafeOnlineWorkspaceFactory(
        runtime_root=tmp_path / "runtime",
        baseline_root=baseline,
    )
    handle = factory.get_or_create(InMemoryOnlineSessionStore().get_or_create(None))
    outside = tmp_path / "outside"
    outside.mkdir()
    simulated_symlink = handle.root / "outside-link"
    simulated_symlink.mkdir()
    original_resolve = Path.resolve

    def resolve_with_escape(path: Path, *args: object, **kwargs: object) -> Path:
        if path == simulated_symlink or simulated_symlink in path.parents:
            return outside / path.relative_to(simulated_symlink)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_with_escape)

    with pytest.raises(OnlineWorkspaceError) as traversal:
        factory.resolve_workspace_path(handle, "../escape.txt")
    with pytest.raises(OnlineWorkspaceError) as absolute:
        factory.resolve_workspace_path(handle, str(outside))
    with pytest.raises(OnlineWorkspaceError) as link_escape:
        factory.resolve_workspace_path(handle, "outside-link/file.txt")

    assert traversal.value.code == ONLINE_SAFE_USER_PATH_ERROR
    assert absolute.value.code == ONLINE_SAFE_USER_PATH_ERROR
    assert link_escape.value.code == ONLINE_SAFE_WORKSPACE_BOUNDARY_ERROR


def test_workspace_baseline_symlink_and_limits_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    baseline = _baseline(tmp_path)
    symlink_baseline = tmp_path / "symlink-baseline"
    symlink_baseline.mkdir()
    (symlink_baseline / "README.md").write_text("ok\n", encoding="utf-8")
    simulated_link = symlink_baseline / "escape"
    simulated_link.write_text("escape\n", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def is_symlink_for_escape(path: Path) -> bool:
        return path == simulated_link or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink_for_escape)

    with pytest.raises(OnlineWorkspaceError) as symlink_error:
        SafeOnlineWorkspaceFactory(
            runtime_root=tmp_path / "runtime-symlink",
            baseline_root=symlink_baseline,
        ).get_or_create(InMemoryOnlineSessionStore().get_or_create(None))
    with pytest.raises(OnlineWorkspaceError) as file_limit:
        SafeOnlineWorkspaceFactory(
            runtime_root=tmp_path / "runtime-files",
            baseline_root=baseline,
            max_files=1,
        ).get_or_create(InMemoryOnlineSessionStore().get_or_create(None))
    with pytest.raises(OnlineWorkspaceError) as byte_limit:
        SafeOnlineWorkspaceFactory(
            runtime_root=tmp_path / "runtime-bytes",
            baseline_root=baseline,
            max_bytes=1,
        ).get_or_create(InMemoryOnlineSessionStore().get_or_create(None))

    assert symlink_error.value.code == ONLINE_SAFE_WORKSPACE_BASELINE_ERROR
    assert file_limit.value.code == ONLINE_SAFE_WORKSPACE_LIMIT_ERROR
    assert byte_limit.value.code == ONLINE_SAFE_WORKSPACE_LIMIT_ERROR
    assert ONLINE_SAFE_WORKSPACE_MAX_BYTES == 100 * 1024 * 1024
    assert ONLINE_SAFE_WORKSPACE_MAX_FILES == 5000


def test_runtime_workspace_api_is_current_session_only_and_preserves_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver({"api.example.test": ["93.184.216.34"]}),
    )
    client_a = TestClient(app_module.create_app(), base_url="https://testserver")
    client_b = TestClient(app_module.create_app(), base_url="https://testserver")
    client_a.get("/api/credentials/llm/status")
    client_a.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )

    workspace_a = client_a.get("/api/runtime/workspace")
    repeat_a = client_a.get("/api/runtime/workspace")
    workspace_b = client_b.get("/api/runtime/workspace")
    reset_a = client_a.post("/api/runtime/workspace/reset")
    status_after_reset = client_a.get("/api/credentials/llm/status")
    session_id = client_a.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    payload_text = str(workspace_a.json())
    workspace_a_id = workspace_a.json()["data"]["workspace"]["id"]

    assert workspace_a.status_code == 200
    assert workspace_a.json()["data"]["ready"] is True
    assert repeat_a.json()["data"]["workspace"]["id"] == workspace_a_id
    assert workspace_b.json()["data"]["workspace"]["id"] != workspace_a_id
    assert reset_a.status_code == 200
    assert reset_a.json()["data"]["workspace"]["id"] == workspace_a_id
    assert status_after_reset.json()["data"]["configured"] is True
    assert runtime_module.get_online_session_store().credential_for(session_id) is not None
    assert str(tmp_path) not in payload_text
    assert session_id not in payload_text


def _baseline(tmp_path: Path) -> Path:
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "README.md").write_text("baseline\n", encoding="utf-8")
    (baseline / "app.py").write_text("print('baseline')\n", encoding="utf-8")
    (baseline / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (baseline / "credentials.json").write_text('{"key":"secret"}\n', encoding="utf-8")
    (baseline / "__pycache__").mkdir()
    (baseline / "__pycache__" / "app.pyc").write_bytes(b"secret")
    return baseline


def _resolver(hosts: dict[str, list[str]]):
    def resolve(host: str, port: int | None, *args: object):
        return [
            (
                0,
                0,
                0,
                "",
                (address, port or 443),
            )
            for address in hosts[host.lower().rstrip(".")]
        ]

    return resolve


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
    import se_mentor.api.runtime as runtime
    import se_mentor.api.runtime_workspace as runtime_workspace_api
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    credentials_api = importlib.reload(credentials_api)
    runtime_workspace_api = importlib.reload(runtime_workspace_api)
    main = importlib.reload(main)
    return main, runtime
