from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from se_mentor.api.envelope import ok

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalDecisionPayload(BaseModel):
    approved_scope: list[str] = Field(default_factory=list, alias="approvedScope")


@router.post("/{approval_id}/approve")
def approve(approval_id: str, payload: ApprovalDecisionPayload) -> dict[str, object]:
    return ok({"id": approval_id, "status": "APPROVED", "approvedScope": payload.approved_scope})


@router.post("/{approval_id}/reject")
def reject(approval_id: str) -> dict[str, object]:
    return ok({"id": approval_id, "status": "REJECTED"})
