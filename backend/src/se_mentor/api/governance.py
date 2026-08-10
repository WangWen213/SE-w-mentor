from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from se_mentor.api.envelope import error, ok
from se_mentor.api.state import STATE

router = APIRouter(prefix="/api/proposals", tags=["governance"])


class GovernanceRequest(BaseModel):
    changed_paths: list[str] = Field(alias="changedPaths")


@router.post("/{proposal_id}/governance")
def run_governance(
    proposal_id: str,
    payload: GovernanceRequest,
    response: Response,
) -> dict[str, object]:
    proposal = _find_proposal(proposal_id)
    if proposal is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return error("PROPOSAL_NOT_FOUND", "proposal not found")
    if proposal.get("status") != "CONFIRMED":
        response.status_code = status.HTTP_409_CONFLICT
        return error("PROPOSAL_NOT_CONFIRMED", "confirm proposal before governance")
    decision = "BLOCK" if any(".env" in path for path in payload.changed_paths) else "ALLOW"
    data = {
        "proposalId": proposal_id,
        "decision": decision,
        "changedPaths": sorted(payload.changed_paths),
        "evidenceRef": "evidence://governance/mock",
    }
    return ok(data)


def _find_proposal(proposal_id: str) -> dict[str, object] | None:
    for proposals in STATE.proposals.values():
        for proposal in proposals:
            if proposal["id"] == proposal_id:
                return proposal
    return None
