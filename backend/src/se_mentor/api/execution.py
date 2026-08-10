from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks", tags=["execution"])


class ExecuteRequest(BaseModel):
    command: str


@router.post("/{task_id}/execute")
def execute(task_id: str, payload: ExecuteRequest, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    if task.get("status") == "BLOCKED":
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = int(task.get("toolCalls", 0))
        return error("TASK_BLOCKED", "blocked tasks cannot execute tools")
    task["toolCalls"] = int(task.get("toolCalls", 0)) + 1
    task["status"] = "EXECUTING"
    return ok({"taskId": task_id, "command": payload.command, "status": "EXECUTING"})


@router.get("/{task_id}/policy")
def policy(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    return ok({"taskId": task_id, "writePaths": [], "commands": []})
