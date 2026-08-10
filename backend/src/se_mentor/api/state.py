from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class ApiState:
    projects: dict[str, dict[str, object]] = field(default_factory=dict)
    tasks: dict[str, dict[str, object]] = field(default_factory=dict)
    proposals: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    replay: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    file_changes: dict[str, dict[str, object]] = field(default_factory=dict)

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4()}"


STATE = ApiState()
