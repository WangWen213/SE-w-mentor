from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from se_mentor.security.secrets import CredentialProvider, Secret

SERVICE_NAME = "se-mentor-openai"


class KeyringUnavailable(RuntimeError):
    pass


class Keyring(Protocol):
    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


@dataclass(frozen=True)
class CredentialStatus:
    profile_id: str
    has_key: bool
    persistence: str
    secret_value: None = None

    def __repr__(self) -> str:
        return (
            "CredentialStatus("
            f"profile_id={self.profile_id!r}, "
            f"has_key={self.has_key!r}, "
            f"persistence={self.persistence!r}, "
            "secret_value=[REDACTED])"
        )


class InMemoryKeyring:
    def __init__(self, *, fail_operations: bool = False) -> None:
        self.fail_operations = fail_operations
        self._values: dict[tuple[str, str], str] = {}

    def set_password(self, service_name: str, username: str, password: str) -> None:
        if self.fail_operations:
            raise KeyringUnavailable("keyring unavailable")
        self._values[(service_name, username)] = password

    def get_password(self, service_name: str, username: str) -> str | None:
        if self.fail_operations:
            raise KeyringUnavailable("keyring unavailable")
        return self._values.get((service_name, username))

    def delete_password(self, service_name: str, username: str) -> None:
        if self.fail_operations:
            raise KeyringUnavailable("keyring unavailable")
        self._values.pop((service_name, username), None)


class CredentialStore:
    def __init__(self, *, profile_id: str, keyring: Keyring) -> None:
        self.profile_id = profile_id
        self.keyring = keyring
        self._session_value: str | None = None
        self._persistence = "keyring"

    @property
    def credential_ref(self) -> str:
        return f"openai:{self.profile_id}"

    def set_api_key(self, value: str) -> CredentialStatus:
        if not value:
            raise ValueError("credential value must not be empty")
        try:
            self.keyring.set_password(SERVICE_NAME, self.profile_id, value)
            self._session_value = None
            self._persistence = "keyring"
        except KeyringUnavailable:
            self._session_value = value
            self._persistence = "session"
        return self.status()

    def update_api_key(self, value: str) -> CredentialStatus:
        return self.set_api_key(value)

    def clear_api_key(self) -> CredentialStatus:
        self._session_value = None
        try:
            self.keyring.delete_password(SERVICE_NAME, self.profile_id)
            self._persistence = "keyring"
        except KeyringUnavailable:
            self._persistence = "session"
        return self.status()

    def status(self) -> CredentialStatus:
        return CredentialStatus(
            profile_id=self.profile_id,
            has_key=self._get_value() is not None,
            persistence=self._persistence,
        )

    def db_record(self) -> dict[str, str]:
        return {"profile_id": self.profile_id, "credential_ref": self.credential_ref}

    def provider(self) -> CredentialProvider:
        return CredentialProvider(self._secret_for)

    def require_persistent_credentials(self) -> None:
        if self._persistence != "keyring":
            raise KeyringUnavailable("persistent keyring unavailable")

    def _secret_for(self, name: str) -> Secret:
        if name != "openai":
            raise KeyError(name)
        value = self._get_value()
        if value is None:
            raise KeyError(name)
        return Secret(value)

    def _get_value(self) -> str | None:
        if self._session_value is not None:
            return self._session_value
        try:
            return self.keyring.get_password(SERVICE_NAME, self.profile_id)
        except KeyringUnavailable:
            self._persistence = "session"
            return None
