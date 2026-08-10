from __future__ import annotations

import json
from typing import Protocol

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.api.envelope import error, ok
from se_mentor.approvals.decision_service import ApprovalDecisionService
from se_mentor.db.session import session_scope
from se_mentor.models.approval import (
    ApprovalDecisionOutcome,
    ApprovalRequest,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.policy.compiler import ExecutionPolicyCompiler
from se_mentor.policy.grants import TemporaryGrantService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
_SESSION_FACTORY: sessionmaker[Session] | None = None


class ApprovalDecisionPayload(BaseModel):
    approved_scope: list[str] = Field(default_factory=list, alias="approvedScope")


class ApprovalAuthority(Protocol):
    def approve(
        self, *, approval_id: str, approved_scope: tuple[str, ...]
    ) -> dict[str, object]: ...


class BackendApprovalAuthority:
    def __init__(self, session_factory: sessionmaker[Session] | None) -> None:
        self._session_factory = session_factory

    def approve(self, *, approval_id: str, approved_scope: tuple[str, ...]) -> dict[str, object]:
        if self._session_factory is None:
            raise ValueError("approval authority unavailable")
        with session_scope(self._session_factory) as session:
            request = session.get(ApprovalRequest, approval_id)
            if request is None:
                raise ValueError("approval request not found")
            decision = ApprovalDecisionService(session).record(
                task_id=request.task_id,
                request_id=approval_id,
                approver_id="api-user",
                outcome=ApprovalDecisionOutcome.APPROVED,
                approved_scope=approved_scope,
            )
            policy = _active_policy_for_request(session, request)
            if policy is None:
                policy = ExecutionPolicyCompiler(session).compile(
                    governance_decision_id=request.governance_decision_id,
                    read_paths=(),
                    write_paths=approved_scope,
                    commands=("RUN_COMMAND",),
                    protected_paths=(),
                    network={},
                    resource_limits={},
                )
            commands = _json_tuple(policy.commands_json)
            grant = TemporaryGrantService(session).create(
                policy.id,
                write_paths=approved_scope,
                commands=commands,
            )
            return {
                "id": approval_id,
                "status": decision.outcome,
                "approvedScope": list(approved_scope),
                "temporaryGrant": {
                    "id": grant.policy_id,
                    "approvalId": approval_id,
                    "scope": list(grant.write_paths),
                    "status": "ACTIVE",
                    "taskId": grant.task_id,
                    "policyId": grant.policy_id,
                    "revision": grant.revision,
                },
                "executionPolicy": {
                    "id": policy.id,
                    "approvalId": approval_id,
                    "writeAllowed": bool(policy.executable and grant.write_paths),
                    "commands": list(grant.commands),
                    "writePaths": list(grant.write_paths),
                    "status": policy.status,
                },
            }


def set_session_factory(session_factory: sessionmaker[Session] | None) -> None:
    global _SESSION_FACTORY
    _SESSION_FACTORY = session_factory


def get_approval_authority() -> ApprovalAuthority:
    return BackendApprovalAuthority(_SESSION_FACTORY)


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str, payload: ApprovalDecisionPayload, response: Response
) -> dict[str, object]:
    try:
        return ok(
            get_approval_authority().approve(
                approval_id=approval_id,
                approved_scope=tuple(payload.approved_scope),
            )
        )
    except ValueError as exc:
        response.status_code = status.HTTP_409_CONFLICT
        return error("APPROVAL_REJECTED", str(exc))


@router.post("/{approval_id}/reject")
def reject(approval_id: str) -> dict[str, object]:
    return ok({"id": approval_id, "status": "REJECTED"})


def _active_policy_for_request(
    session: Session, request: ApprovalRequest
) -> ExecutionPolicy | None:
    return session.scalar(
        select(ExecutionPolicy)
        .where(ExecutionPolicy.approval_request_id == request.id)
        .where(ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE)
    )


def _json_tuple(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data)
