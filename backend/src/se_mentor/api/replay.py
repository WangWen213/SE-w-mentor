from __future__ import annotations

from fastapi import APIRouter, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks", tags=["replay"])


@router.get("/{task_id}/replay")
def replay(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    events = sorted(STATE.replay.get(task_id, []), key=lambda item: int(item["eventId"]))
    return ok({"taskId": task_id, "events": events})
