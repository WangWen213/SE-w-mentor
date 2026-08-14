from __future__ import annotations

import json

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import PlainTextResponse

from se_mentor.api.envelope import error
from se_mentor.api.online_access import require_task_access
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.events.bus import EventBus

router = APIRouter(prefix="/api/tasks", tags=["events"])
BUS = EventBus()
_SESSION_FACTORY = get_session_factory()


@router.get("/{task_id}/events", response_model=None)
def events(
    task_id: str,
    request: Request,
    response: Response,
    last_event_id: str | None = Header(default=None),
) -> object:
    with session_scope(_SESSION_FACTORY) as session:
        if require_task_access(session, task_id, request, response) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
    last_id = int(last_event_id) if last_event_id else None
    body = "".join(
        (
            f"id: {event.event_id}\n"
            f"event: {event.event_type}\n"
            f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
        )
        for event in BUS.replay(task_id=task_id, last_event_id=last_id)
    )
    return PlainTextResponse(body, media_type="text/event-stream")
