from __future__ import annotations

import hashlib

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.api.runtime import (
    get_online_session_store,
    get_online_workspace_factory,
    get_runtime_settings,
)
from se_mentor.models.approval import ApprovalRequest
from se_mentor.models.evaluation import TaskEvaluation
from se_mentor.models.execution import FileChange
from se_mentor.models.governance import GovernanceDecision
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeProposal, ChangeTask
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    OnlineSession,
    OnlineSessionLimitExceeded,
)
from se_mentor.runtime.profiles import RuntimeProfile


class OnlineSessionUnavailable(RuntimeError):
    pass


def online_owner_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def current_online_session(request: Request, response: Response) -> OnlineSession:
    try:
        session = get_online_session_store().get_or_create(
            request.cookies.get(ONLINE_SESSION_COOKIE_NAME)
        )
    except OnlineSessionLimitExceeded as exc:
        raise OnlineSessionUnavailable("active session limit reached") from exc
    get_online_workspace_factory().cleanup_expired(get_online_session_store().active_session_ids())
    response.set_cookie(
        key=ONLINE_SESSION_COOKIE_NAME,
        value=session.session_id,
        max_age=get_online_session_store().ttl_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return session


def current_online_owner_hash(request: Request, response: Response) -> str:
    return online_owner_hash(current_online_session(request, response).session_id)


def online_project_filter(statement, request: Request, response: Response):
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return statement
    return statement.where(
        Project.owner_session_hash == current_online_owner_hash(request, response)
    )


def require_project_access(
    db: Session,
    project_id: str,
    request: Request,
    response: Response,
) -> Project | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(Project, project_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_task_access(
    db: Session,
    task_id: str,
    request: Request,
    response: Response,
) -> ChangeTask | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(ChangeTask, task_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(ChangeTask)
        .join(Project, ChangeTask.project_id == Project.id)
        .where(ChangeTask.id == task_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_proposal_access(
    db: Session,
    proposal_id: str,
    request: Request,
    response: Response,
) -> ChangeProposal | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(ChangeProposal, proposal_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(ChangeProposal)
        .join(ChangeTask, ChangeProposal.task_id == ChangeTask.id)
        .join(Project, ChangeTask.project_id == Project.id)
        .where(ChangeProposal.id == proposal_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_governance_decision_access(
    db: Session,
    decision_id: str,
    request: Request,
    response: Response,
) -> GovernanceDecision | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(GovernanceDecision, decision_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(GovernanceDecision)
        .join(ChangeTask, GovernanceDecision.task_id == ChangeTask.id)
        .join(Project, ChangeTask.project_id == Project.id)
        .where(GovernanceDecision.id == decision_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_approval_access(
    db: Session,
    approval_id: str,
    request: Request,
    response: Response,
) -> ApprovalRequest | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(ApprovalRequest, approval_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(ApprovalRequest)
        .join(ChangeTask, ApprovalRequest.task_id == ChangeTask.id)
        .join(Project, ChangeTask.project_id == Project.id)
        .where(ApprovalRequest.id == approval_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_evaluation_access(
    db: Session,
    evaluation_id: str,
    request: Request,
    response: Response,
) -> TaskEvaluation | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(TaskEvaluation, evaluation_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(TaskEvaluation)
        .join(Project, TaskEvaluation.project_id == Project.id)
        .where(TaskEvaluation.id == evaluation_id)
        .where(Project.owner_session_hash == owner_hash)
    )


def require_file_change_access(
    db: Session,
    change_id: str,
    request: Request,
    response: Response,
) -> FileChange | None:
    if get_runtime_settings().profile is not RuntimeProfile.ONLINE_SAFE:
        return db.get(FileChange, change_id)
    owner_hash = current_online_owner_hash(request, response)
    return db.scalar(
        select(FileChange)
        .join(ChangeTask, FileChange.task_id == ChangeTask.id)
        .join(Project, ChangeTask.project_id == Project.id)
        .where(FileChange.id == change_id)
        .where(Project.owner_session_hash == owner_hash)
    )
