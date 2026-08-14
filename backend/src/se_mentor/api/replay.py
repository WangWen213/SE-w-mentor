from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_task_access
from se_mentor.api.runtime import get_session_factory
from se_mentor.api.state import STATE
from se_mentor.db.session import session_scope

router = APIRouter(prefix="/api/tasks", tags=["replay"])
_SESSION_FACTORY = get_session_factory()


def _event_id(event: dict[str, object]) -> int:
    value = event.get("eventId", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


@router.get("/{task_id}/replay")
def replay(task_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if require_task_access(session, task_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    events = sorted(STATE.replay.get(task_id, []), key=_event_id)
    return ok({"taskId": task_id, "events": events})
