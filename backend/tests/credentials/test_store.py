from __future__ import annotations

import pytest

from se_mentor.credentials.store import (
    CredentialStore,
    InMemoryKeyring,
    KeyringUnavailable,
)


def test_T104_set_update_clear_never_persists_or_prints_secret() -> None:
    keyring = InMemoryKeyring()
    store = CredentialStore(profile_id="default", keyring=keyring)

    result = store.set_api_key("sk-proj-first")
    provider = store.provider()

    assert result.profile_id == "default"
    assert result.has_key is True
    assert result.secret_value is None
    assert "sk-proj" not in repr(result)
    assert store.db_record() == {"profile_id": "default", "credential_ref": "openai:default"}
    assert provider.get_secret_value("openai") == "sk-proj-first"

    updated = store.update_api_key("sk-proj-second")

    assert updated.has_key is True
    assert updated.secret_value is None
    assert provider.get_secret_value("openai") == "sk-proj-second"
    assert "sk-proj" not in repr(store.status())

    cleared = store.clear_api_key()

    assert cleared.has_key is False
    with pytest.raises(KeyError):
        provider.get_secret_value("openai")

    unavailable = CredentialStore(
        profile_id="session",
        keyring=InMemoryKeyring(fail_operations=True),
    )
    session_status = unavailable.set_api_key("sk-proj-session")

    assert session_status.has_key is True
    assert session_status.persistence == "session"
    assert unavailable.db_record() == {
        "profile_id": "session",
        "credential_ref": "openai:session",
    }
    assert unavailable.provider().get_secret_value("openai") == "sk-proj-session"
    with pytest.raises(KeyringUnavailable):
        unavailable.require_persistent_credentials()
