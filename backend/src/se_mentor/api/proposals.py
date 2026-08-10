from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/tasks/{task_id}/proposals", tags=["proposals"])


class ProposalCreate(BaseModel):
    goal: str
    missing_information_question: str | None = Field(
        default=None,
        alias="missingInformationQuestion",
    )


class ProposalAdjust(BaseModel):
    instruction: str


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
        "items": ["分析当前范围", "形成修改方案"],
        "impact": "待分析",
        "risk": "需先分析治理，不会立即修改",
        "missingInformationQuestion": payload.missing_information_question,
        "status": "DRAFT",
    }
    if payload.missing_information_question:
        STATE.tasks[task_id]["status"] = "NEEDS_INFORMATION"
    STATE.proposals[task_id].append(proposal)
    return ok(proposal)


@router.get("")
def current_proposal(task_id: str, response: Response) -> dict[str, object]:
    if task_id not in STATE.tasks:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("TASK_NOT_FOUND", "task not found")
    proposals = STATE.proposals.get(task_id, [])
    if not proposals:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    return ok(dict(proposals[-1]))


@router.post("/{proposal_id}/confirm")
def confirm_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    proposal = _proposal(task_id, proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    proposal["status"] = "CONFIRMED"
    STATE.tasks[task_id]["status"] = "PROPOSAL_CONFIRMED"
    return ok(proposal)


@router.post("/{proposal_id}/reject")
def reject_proposal(task_id: str, proposal_id: str, response: Response) -> dict[str, object]:
    proposal = _proposal(task_id, proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    proposal["status"] = "REJECTED"
    STATE.tasks[task_id]["status"] = "CANCELLED"
    return ok(proposal)


@router.post("/{proposal_id}/adjust")
def adjust_proposal(
    task_id: str,
    proposal_id: str,
    payload: ProposalAdjust,
    response: Response,
) -> dict[str, object]:
    proposal = _proposal(task_id, proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    if not payload.instruction.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("PROPOSAL_ADJUSTMENT_REQUIRED", "proposal adjustment is required")
    proposal["status"] = "SUPERSEDED"
    version = len(STATE.proposals.setdefault(task_id, [])) + 1
    adjusted = {
        "id": STATE.new_id("proposal"),
        "taskId": task_id,
        "version": version,
        "goal": payload.instruction,
        "items": ["按补充意见重新整理方案", "等待你再次确认"],
        "impact": "待分析",
        "risk": "需先分析治理，不会立即修改",
        "missingInformationQuestion": None,
        "status": "DRAFT",
    }
    STATE.proposals[task_id].append(adjusted)
    STATE.tasks[task_id]["status"] = "CREATED"
    return ok(adjusted)


def _proposal(task_id: str, proposal_id: str) -> dict[str, object] | None:
    for proposal in STATE.proposals.get(task_id, []):
        if proposal["id"] == proposal_id:
            return proposal
    return None
