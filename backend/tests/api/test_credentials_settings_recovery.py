from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from se_mentor.credentials.store import CredentialStore, InMemoryKeyring


def test_openai_compatible_provider_status_is_safe_and_update_keeps_existing_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "LOCAL_FULL")
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.runtime as runtime
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    credentials_api = importlib.reload(credentials_api)
    main = importlib.reload(main)
    store = CredentialStore(profile_id="default", keyring=InMemoryKeyring())
    monkeypatch.setattr(runtime, "_CREDENTIAL_STORE", store)
    runtime.clear_provider_config()
    client = TestClient(main.create_app())

    created = client.post(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": "sk-test-secret",
            "baseUrl": "https://api.example.test/v1",
            "model": "model-a",
        },
    )
    status = client.get("/api/credentials/llm/status")
    updated = client.put(
        "/api/credentials/llm",
        json={
            "provider": "openai-compatible",
            "key": "",
            "baseUrl": "https://api.example.test/v1",
            "model": "model-b",
        },
    )

    assert created.status_code == 200
    assert status.status_code == 200
    assert status.json()["data"]["configured"] is True
    assert "key" not in status.json()["data"]
    assert "sk-test-secret" not in str(status.json())
    assert updated.status_code == 200
    assert updated.json()["data"]["configured"] is True
    assert updated.json()["data"]["model"] == "model-b"
    assert store.provider().get_secret_value("openai") == "sk-test-secret"
    assert credentials_api.get_runtime_settings().profile.value == "LOCAL_FULL"
