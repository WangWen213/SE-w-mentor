from __future__ import annotations

from fastapi import APIRouter, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/diffs", tags=["diffs"])


@router.get("/{change_id}/trace")
def trace_change(change_id: str, response: Response) -> dict[str, object]:
    change = STATE.file_changes.get(change_id)
    if change is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("FILE_CHANGE_NOT_FOUND", "file change not found")
    return ok(dict(change))
