from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import sys
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol

from se_mentor.security.secrets import CredentialProvider, Secret

SERVICE_NAME = "se-mentor-openai"
METADATA_SUFFIX = ":metadata"


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


class SystemKeyring:
    def __init__(self) -> None:
        try:
            self._keyring = import_module("keyring")
        except Exception as exc:
            raise KeyringUnavailable("keyring package unavailable") from exc

    def set_password(self, service_name: str, username: str, password: str) -> None:
        try:
            self._keyring.set_password(service_name, username, password)
        except Exception as exc:
            raise KeyringUnavailable("keyring set failed") from exc

    def get_password(self, service_name: str, username: str) -> str | None:
        try:
            value = self._keyring.get_password(service_name, username)
        except Exception as exc:
            raise KeyringUnavailable("keyring get failed") from exc
        return value if isinstance(value, str) else None

    def delete_password(self, service_name: str, username: str) -> None:
        try:
            self._keyring.delete_password(service_name, username)
        except Exception as exc:
            raise KeyringUnavailable("keyring delete failed") from exc


class WindowsCredentialManagerKeyring:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise KeyringUnavailable("Windows Credential Manager is unavailable on this platform")
        self._advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)

    def set_password(self, service_name: str, username: str, password: str) -> None:
        target = _target_name(service_name, username)
        encoded = password.encode("utf-16-le")
        credential = _CREDENTIALW()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(
            ctypes.create_string_buffer(encoded),
            ctypes.POINTER(ctypes.c_byte),
        )
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = username
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise KeyringUnavailable(_last_windows_error("CredWriteW"))

    def get_password(self, service_name: str, username: str) -> str | None:
        credential_ptr = ctypes.POINTER(_CREDENTIALW)()
        target = _target_name(service_name, username)
        if not self._advapi32.CredReadW(
            target,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_ptr),
        ):
            error_code = ctypes.get_last_error()
            if error_code == 1168:
                return None
            raise KeyringUnavailable(_windows_error("CredReadW", error_code))
        try:
            credential = credential_ptr.contents
            blob_size = int(credential.CredentialBlobSize)
            if blob_size <= 0:
                return None
            raw = ctypes.string_at(credential.CredentialBlob, blob_size)
            return raw.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(credential_ptr)

    def delete_password(self, service_name: str, username: str) -> None:
        if not self._advapi32.CredDeleteW(
            _target_name(service_name, username),
            self.CRED_TYPE_GENERIC,
            0,
        ):
            error_code = ctypes.get_last_error()
            if error_code != 1168:
                raise KeyringUnavailable(_windows_error("CredDeleteW", error_code))


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class CredentialStore:
    def __init__(self, *, profile_id: str, keyring: Keyring) -> None:
        self.profile_id = profile_id
        self.keyring = keyring
        self._session_value: str | None = None
        self._session_metadata: dict[str, str | None] = {}
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

    def set_provider_metadata(self, *, base_url: str | None, model: str | None) -> None:
        metadata = {"base_url": base_url, "model": model}
        try:
            self.keyring.set_password(
                SERVICE_NAME,
                f"{self.profile_id}{METADATA_SUFFIX}",
                json.dumps(metadata, sort_keys=True),
            )
            self._session_metadata = {}
            self._persistence = "keyring"
        except KeyringUnavailable:
            self._session_metadata = metadata
            self._persistence = "session"

    def clear_provider_metadata(self) -> None:
        self._session_metadata = {}
        try:
            self.keyring.delete_password(SERVICE_NAME, f"{self.profile_id}{METADATA_SUFFIX}")
            self._persistence = "keyring"
        except KeyringUnavailable:
            self._persistence = "session"

    def provider_metadata(self) -> dict[str, str | None]:
        if self._session_metadata:
            return dict(self._session_metadata)
        try:
            raw = self.keyring.get_password(SERVICE_NAME, f"{self.profile_id}{METADATA_SUFFIX}")
        except KeyringUnavailable:
            self._persistence = "session"
            return {}
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            "base_url": data.get("base_url") if isinstance(data.get("base_url"), str) else None,
            "model": data.get("model") if isinstance(data.get("model"), str) else None,
        }

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


def _target_name(service_name: str, username: str) -> str:
    return f"{service_name}:{username}"


def _last_windows_error(api_name: str) -> str:
    return _windows_error(api_name, ctypes.get_last_error())


def _windows_error(api_name: str, error_code: int) -> str:
    return f"{api_name} failed with Windows error {error_code}"
