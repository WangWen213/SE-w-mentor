from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from se_mentor.security.redaction import redact_text


@dataclass(frozen=True)
class Event:
    event_id: int
    task_id: str
    event_type: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._next_id = 1

    def publish(self, *, task_id: str, event_type: str, payload: dict[str, Any]) -> Event:
        event = Event(
            event_id=self._next_id,
            task_id=task_id,
            event_type=event_type,
            payload={key: _sanitize(value) for key, value in payload.items()},
        )
        self._next_id += 1
        self._events.append(event)
        return event

    def replay(self, *, task_id: str, last_event_id: int | None = None) -> tuple[Event, ...]:
        since = int(last_event_id or 0)
        return tuple(
            event for event in self._events if event.task_id == task_id and event.event_id > since
        )


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    return value
