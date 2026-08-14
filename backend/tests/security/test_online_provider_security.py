from __future__ import annotations

import importlib
import socket
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_mentor.runtime.online_provider_security import (
    ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED,
    ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
    ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
    ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED,
    ONLINE_SAFE_PROVIDER_TRANSPORT_REQUIRED,
    OnlineProviderEndpointError,
    OnlineProviderEndpointPolicy,
)
from se_mentor.runtime.online_sessions import ONLINE_SESSION_COOKIE_NAME

ONLINE_SAFE_TEST_KEY = "test-online-safe-secret-value"


def test_online_endpoint_policy_rejects_ssrf_targets_and_accepts_public_hosts() -> None:
    policy = OnlineProviderEndpointPolicy(
        resolver=_resolver({"api.example.test": ["93.184.216.34"]})
    )

    matrix = {
        "http://api.example.test/v1": ONLINE_SAFE_PROVIDER_TRANSPORT_REQUIRED,
        "https://127.0.0.1/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://[::1]/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://10.0.0.1/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://172.16.0.1/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://192.168.1.1/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://169.254.169.254/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://[fc00::1]/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://localhost/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "https://user:password@api.example.test/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
        "https://example.com@127.0.0.1/v1": ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
        "https:///v1": ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
    }

    for url, code in matrix.items():
        with pytest.raises(OnlineProviderEndpointError) as exc:
            policy.validate(url)
        assert exc.value.code == code

    endpoint = policy.validate("https://api.example.test:8443/v1/chat/completions")

    assert endpoint.base_url == "https://api.example.test:8443/v1"
    assert endpoint.port == 8443
    assert endpoint.resolved_addresses == ("93.184.216.34",)


def test_online_endpoint_policy_rejects_mixed_dns_and_resolution_failure() -> None:
    mixed_policy = OnlineProviderEndpointPolicy(
        resolver=_resolver({"mixed.example.test": ["93.184.216.34", "10.0.0.2"]})
    )
    failing_policy = OnlineProviderEndpointPolicy(resolver=_failing_resolver)

    with pytest.raises(OnlineProviderEndpointError) as mixed_error:
        mixed_policy.validate("https://mixed.example.test/v1")
    with pytest.raises(OnlineProviderEndpointError) as dns_error:
        failing_policy.validate("https://missing.example.test/v1")

    assert mixed_error.value.code == ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN
    assert dns_error.value.code == ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED


def test_online_safe_credential_endpoint_validates_endpoint_before_replace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, _, credentials_api, runtime_module, _ = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver({"api.example.test": ["93.184.216.34"]}),
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    client.get("/api/credentials/llm/status")

    created = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": f"{ONLINE_SAFE_TEST_KEY}-a",
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    rejected = client.put(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": f"{ONLINE_SAFE_TEST_KEY}-b",
            "baseUrl": "https://127.0.0.1/v1",
            "model": "model-b",
        },
    )
    status_response = client.get("/api/credentials/llm/status")
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)
    credential = runtime_module.get_online_session_store().credential_for(session_id)

    assert created.status_code == 200
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN
    assert status_response.json()["data"]["baseUrl"] == "https://api.example.test/v1"
    assert status_response.json()["data"]["model"] == "model-a"
    assert credential is not None
    assert credential.secret.reveal() == f"{ONLINE_SAFE_TEST_KEY}-a"
    assert credentials_api.get_runtime_settings().profile.value == "ONLINE_SAFE"


def test_online_safe_provider_construction_is_session_scoped_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    _, _, _, runtime_module, _ = _reload_api_for_online_safe(monkeypatch, tmp_path / "runtime")
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver(
            {
                "a.example.test": ["93.184.216.34"],
                "b.example.test": ["93.184.216.35"],
            }
        ),
    )
    store = runtime_module.get_online_session_store()
    session_a = store.get_or_create(None)
    session_b = store.get_or_create(None)
    store.set_credential(
        session_a.session_id,
        provider="openai-compatible",
        base_url="https://a.example.test/v1",
        model="model-a",
        key=f"{ONLINE_SAFE_TEST_KEY}-a",
    )
    store.set_credential(
        session_b.session_id,
        provider="openai-compatible",
        base_url="https://b.example.test/v1",
        model="model-b",
        key=f"{ONLINE_SAFE_TEST_KEY}-b",
    )

    class FailingStore:
        def provider(self):
            raise AssertionError("ONLINE_SAFE provider must not read global credentials")

        def provider_metadata(self):
            raise AssertionError("ONLINE_SAFE provider must not read global metadata")

    monkeypatch.setattr(runtime_module, "_CREDENTIAL_STORE", FailingStore())
    with pytest.raises(runtime_module.OnlineSafeNotReadyError) as no_session:
        runtime_module.get_online_session_provider(None)
    no_credential = store.get_or_create(None)
    with pytest.raises(runtime_module.OnlineSafeNotReadyError) as missing_credential:
        runtime_module.get_online_session_provider(no_credential.session_id)

    provider_a = runtime_module.get_online_session_provider(session_a.session_id)
    provider_b = runtime_module.get_online_session_provider(session_b.session_id)
    response_a = provider_a.client.responses
    response_b = provider_b.client.responses

    assert str(no_session.value) == runtime_module.ONLINE_SAFE_SESSION_ERROR
    assert str(missing_credential.value) == ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED
    assert provider_a is not provider_b
    assert provider_a.model == "model-a"
    assert provider_b.model == "model-b"
    assert response_a._base_url == "https://a.example.test/v1"
    assert response_b._base_url == "https://b.example.test/v1"
    assert response_a._secret.reveal() == f"{ONLINE_SAFE_TEST_KEY}-a"
    assert response_b._secret.reveal() == f"{ONLINE_SAFE_TEST_KEY}-b"
    assert response_a.allow_redirects is False
    assert response_a.trust_env is False
    assert any(
        handler.__class__.__name__ == "_NoRedirectHandler"
        for handler in response_a._opener.handlers
    )
    assert not any(
        hasattr(handler, "proxy_open") for handler in response_a._opener.handlers
    )


def test_online_safe_public_agent_flow_requires_credential_then_reaches_task_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, _, _, runtime_module, _ = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
    )
    monkeypatch.setattr(
        "se_mentor.runtime.online_provider_security.socket.getaddrinfo",
        _resolver({"api.example.test": ["93.184.216.34"]}),
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    assert runtime_module._ENGINE is not None
    project_id = _import_project(client)["id"]
    missing_credential = client.post(
        "/api/tasks",
        json={"projectId": project_id, "request": "do work"},
    )
    configured = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": ONLINE_SAFE_TEST_KEY,
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    task = client.post("/api/tasks", json={"projectId": project_id, "request": "do work"})

    assert missing_credential.status_code == 409
    assert missing_credential.json()["error"]["code"] == ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED
    assert configured.status_code == 200
    assert task.status_code == 201
    assert task.json()["data"]["projectId"] == project_id


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


def _import_project(client: TestClient) -> dict[str, object]:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("app.py", "print('online')\n")
    return client.post(
        "/api/projects/import-zip",
        content=output.getvalue(),
        headers={"content-type": "application/zip"},
    ).json()["data"]


def _failing_resolver(host: str, port: int | None, *args: object):
    raise socket.gaierror("missing")


def _reload_api_for_online_safe(monkeypatch: pytest.MonkeyPatch, runtime_root: Path):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    monkeypatch.setenv("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.execution as execution_api
    import se_mentor.api.online_readiness as online_readiness_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.proposals as proposals_api
    import se_mentor.api.runtime as runtime
    import se_mentor.api.tasks as tasks_api
    import se_mentor.execution.orchestrator as orchestrator_module
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    importlib.reload(online_readiness_api)
    projects_api = importlib.reload(projects_api)
    credentials_api = importlib.reload(credentials_api)
    tasks_api = importlib.reload(tasks_api)
    proposals_api = importlib.reload(proposals_api)
    execution_api = importlib.reload(execution_api)
    orchestrator_module = importlib.reload(orchestrator_module)
    main = importlib.reload(main)
    return main, projects_api, credentials_api, runtime, orchestrator_module
