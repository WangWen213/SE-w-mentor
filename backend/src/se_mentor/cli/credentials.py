from __future__ import annotations

from dataclasses import dataclass

from se_mentor.credentials.store import CredentialStatus, CredentialStore


@dataclass(frozen=True)
class CredentialCommandResult:
    status: CredentialStatus

    def __repr__(self) -> str:
        return f"CredentialCommandResult(status={self.status!r})"


def set_credential(store: CredentialStore, value: str) -> CredentialCommandResult:
    return CredentialCommandResult(status=store.set_api_key(value))


def update_credential(store: CredentialStore, value: str) -> CredentialCommandResult:
    return CredentialCommandResult(status=store.update_api_key(value))


def clear_credential(store: CredentialStore) -> CredentialCommandResult:
    return CredentialCommandResult(status=store.clear_api_key())


def credential_status(store: CredentialStore) -> CredentialCommandResult:
    return CredentialCommandResult(status=store.status())
