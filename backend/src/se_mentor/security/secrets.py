from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class Secret:
    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        self._value = value

    def reveal(self) -> str:
        return self._value

    def to_json_safe(self) -> str:
        return "[REDACTED:SECRET]"

    def model_dump_json(self) -> str:
        return '{"value":"[REDACTED:SECRET]"}'

    def __repr__(self) -> str:
        return "Secret([REDACTED:SECRET])"

    def __str__(self) -> str:
        return "[REDACTED:SECRET]"


class CredentialProvider:
    def __init__(self, callback: Callable[[str], Secret]) -> None:
        self._callback = callback

    def get_secret(self, name: str) -> Secret:
        return self._callback(name)

    def get_secret_value(self, name: str) -> str:
        return self.get_secret(name).reveal()

    def __repr__(self) -> str:
        return "CredentialProvider(callback=[REDACTED])"


@dataclass(frozen=True)
class AgentContext:
    task_id: str
    credential_provider: CredentialProvider = field(repr=False)

    def __repr__(self) -> str:
        return f"AgentContext(task_id={self.task_id!r}, credential_provider=[CALLBACK])"
