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
    decision = _decision_for(payload.changed_paths)
    data = {
        "proposalId": proposal_id,
        "decision": decision,
        "changedPaths": sorted(payload.changed_paths),
        "evidenceRef": "evidence://governance/mock",
        "facts": [
            {
                "summary": "提案影响路径已由后端治理检查记录。",
                "file": path,
                "line": 1,
            }
            for path in sorted(payload.changed_paths)
        ],
        "inferences": _inferences_for(decision),
        "unknowns": _unknowns_for(decision),
        "evidence": [
            {
                "label": "治理规则命中",
                "detail": "后端基于变更路径生成治理决策；前端只展示结果。",
                "file": "governance/rules.yml",
                "line": 1,
            }
        ],
        "impactScope": {
            "files": sorted(payload.changed_paths),
            "summary": _scope_summary(payload.changed_paths),
        },
        "ruleHits": _rule_hits_for(decision),
        "nonApprovable": decision == "BLOCK",
    }
    return ok(data)


def _find_proposal(proposal_id: str) -> dict[str, object] | None:
    for proposals in STATE.proposals.values():
        for proposal in proposals:
            if proposal["id"] == proposal_id:
                return proposal
    return None


def _decision_for(changed_paths: list[str]) -> str:
    if any(".env" in path for path in changed_paths):
        return "BLOCK"
    if any("public" in path or "auth" in path for path in changed_paths):
        return "WARN"
    return "ALLOW"


def _scope_summary(changed_paths: list[str]) -> str:
    count = len(set(changed_paths))
    return f"{count} 个文件受影响"


def _inferences_for(decision: str) -> list[str]:
    if decision == "WARN":
        return ["这次修改可能影响公共行为，需要用户确认范围。"]
    if decision == "BLOCK":
        return ["该操作触及不可批准的敏感路径，不能通过本次授权绕过。"]
    return ["该修改保持在当前方案范围内，可以继续后续治理流程。"]


def _unknowns_for(decision: str) -> list[str]:
    if decision == "WARN":
        return ["尚不能确认所有调用方是否已经同步更新。"]
    return []


def _rule_hits_for(decision: str) -> list[dict[str, str]]:
    labels = {
        "ALLOW": ("自动允许", "普通项目内代码修改"),
        "WARN": ("需要确认", "公共接口或认证相关变化"),
        "BLOCK": ("始终阻止", "敏感凭据或环境文件"),
    }
    level, reason = labels[decision]
    return [{"level": decision, "label": level, "reason": reason}]
