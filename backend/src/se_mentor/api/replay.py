from __future__ import annotations

from fastapi import APIRouter, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks", tags=["replay"])


def _event_id(event: dict[str, object]) -> int:
    value = event.get("eventId", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


@router.get("/{task_id}/replay")
def replay(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    events = sorted(STATE.replay.get(task_id, []), key=_event_id)
    return ok({"taskId": task_id, "events": events})
