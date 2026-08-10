from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import PlainTextResponse

from se_mentor.events.bus import EventBus

router = APIRouter(prefix="/api/tasks", tags=["events"])
BUS = EventBus()


@router.get("/{task_id}/events")
def events(task_id: str, last_event_id: str | None = Header(default=None)) -> PlainTextResponse:
    last_id = int(last_event_id) if last_event_id else None
    body = "".join(
        f"id: {event.event_id}\nevent: {event.event_type}\ndata: {event.payload}\n\n"
        for event in BUS.replay(task_id=task_id, last_event_id=last_id)
    )
    return PlainTextResponse(body, media_type="text/event-stream")
