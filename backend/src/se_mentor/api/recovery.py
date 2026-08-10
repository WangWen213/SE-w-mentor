from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class RecoveryResolve(BaseModel):
    action: str


@router.get("")
def list_recovery() -> dict[str, object]:
    items = [
        {"taskId": task_id, "status": "RECOVERY_REQUIRED", "sideEffects": "unknown"}
        for task_id, task in STATE.tasks.items()
        if task.get("recoveryRequired")
    ]
    return ok({"items": items})


@router.post("/{task_id}/resolve")
def resolve(task_id: str, payload: RecoveryResolve, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    task["recoveryRequired"] = False
    task["recoveryAction"] = payload.action
    return ok({"taskId": task_id, "status": "RESOLVED", "action": payload.action})
