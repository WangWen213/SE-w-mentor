from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks/{task_id}/proposals", tags=["proposals"])


class ProposalCreate(BaseModel):
    goal: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_proposal(task_id: str, payload: ProposalCreate, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    version = len(STATE.proposals.setdefault(task_id, [])) + 1
    proposal = {
        "id": STATE.new_id("proposal"),
        "taskId": task_id,
        "version": version,
        "goal": payload.goal,
        "status": "DRAFT",
    }
    STATE.proposals[task_id].append(proposal)
    return ok(proposal)


@router.post("/{proposal_id}/confirm")
def confirm_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    proposal = _proposal(task_id, proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    proposal["status"] = "CONFIRMED"
    return ok(proposal)


@router.post("/{proposal_id}/reject")
def reject_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    proposal = _proposal(task_id, proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    proposal["status"] = "REJECTED"
    return ok(proposal)


def _proposal(task_id: str, proposal_id: str) -> dict[str, object] | None:
    for proposal in STATE.proposals.get(task_id, []):
        if proposal["id"] == proposal_id:
            return proposal
    return None
