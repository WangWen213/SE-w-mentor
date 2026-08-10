from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from se_mentor.api.envelope import error, ok
from se_mentor.api.events import BUS
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks", tags=["execution"])


class ExecuteRequest(BaseModel):
    command: str


def _tool_calls(task: dict[str, object]) -> int:
    value = task.get("toolCalls", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


@router.post("/{task_id}/execute")
def execute(task_id: str, payload: ExecuteRequest, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    if task.get("status") == "BLOCKED":
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("TASK_BLOCKED", "blocked tasks cannot execute tools")
    if task.get("recoveryRequired"):
        response.status_code = status.HTTP_409_CONFLICT
        task["toolCalls"] = _tool_calls(task)
        return error("RECOVERY_REQUIRED", "resolve recovery before executing tools")
    task["toolCalls"] = _tool_calls(task) + 1
    task["status"] = "EXECUTING"
    event = BUS.publish(
        task_id=task_id,
        event_type="EXECUTION_STARTED",
        payload={
            "projectId": task.get("projectId"),
            "taskId": task_id,
            "state": "EXECUTING",
            "message": "execution started",
        },
    )
    return ok(
        {
            "taskId": task_id,
            "command": payload.command,
            "status": "EXECUTING",
            "eventId": event.event_id,
        }
    )


@router.post("/{task_id}/cancel")
def cancel(task_id: str, response: Response) -> dict[str, object]:
    task = STATE.tasks.get(task_id)
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    task["status"] = "CANCEL_REQUESTED"
    event = BUS.publish(
        task_id=task_id,
        event_type="CANCEL_REQUESTED",
        payload={
            "projectId": task.get("projectId"),
            "taskId": task_id,
            "state": "CANCEL_REQUESTED",
            "message": "cancel requested",
        },
    )
    return ok({"taskId": task_id, "status": "CANCEL_REQUESTED", "eventId": event.event_id})


@router.get("/{task_id}/policy")
def policy(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    return ok({"taskId": task_id, "writePaths": [], "commands": []})
