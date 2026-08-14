from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import online_project_filter, require_task_access
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.models.execution import TaskTransaction, TransactionState
from se_mentor.models.project import Project
from se_mentor.transactions.recovery import TransactionRecoveryService

router = APIRouter(prefix="/api/recovery", tags=["recovery"])
_SESSION_FACTORY = get_session_factory()
LOGGER = logging.getLogger("se_mentor.api.recovery")


class RecoveryResolve(BaseModel):
    action: str


@router.get("")
def list_recovery(request: Request, response: Response) -> dict[str, object]:
    started = perf_counter()
    with session_scope(_SESSION_FACTORY) as session:
        db_started = perf_counter()
        has_unfinished = session.scalar(
            select(TaskTransaction.id)
            .where(
                TaskTransaction.state.in_(
                    [
                        TransactionState.PREPARED,
                        TransactionState.APPLYING,
                        TransactionState.CONFLICT,
                    ]
                )
            )
            .limit(1)
        )
        db_ms = int((perf_counter() - db_started) * 1000)
        if has_unfinished is None:
            total_ms = int((perf_counter() - started) * 1000)
            LOGGER.info(
                "recovery.list mode=cheap db_ms=%s scan_ms=0 total_ms=%s items=0",
                db_ms,
                total_ms,
            )
            return ok({"items": []})
        projects = session.scalars(
            online_project_filter(
                select(Project).order_by(Project.updated_at.desc()),
                request,
                response,
            )
        ).all()
        items: list[dict[str, object]] = []
        scan_started = perf_counter()
        for project in projects:
            summaries = TransactionRecoveryService(
                session,
                project_root=project.root_path,
            ).scan_project(project_id=project.id)
            items.extend(
                {
                    "taskId": summary.task_id,
                    "transactionId": summary.transaction_id,
                    "status": "RECOVERY_REQUIRED",
                    "decision": summary.decision,
                    "sideEffects": "external_changes"
                    if summary.external_changes
                    else "transaction_unfinished",
                    "externalChanges": list(summary.external_changes),
                }
                for summary in summaries
            )
        LOGGER.info(
            "recovery.list mode=scan db_ms=%s scan_ms=%s total_ms=%s items=%s projects=%s",
            db_ms,
            int((perf_counter() - scan_started) * 1000),
            int((perf_counter() - started) * 1000),
            len(items),
            len(projects),
        )
        return ok({"items": items})


@router.post("/{task_id}/resolve")
def resolve(
    task_id: str,
    payload: RecoveryResolve,
    request: Request,
    response: Response,
) -> dict[str, object]:
    if payload.action != "rollback":
        response.status_code = status.HTTP_409_CONFLICT
        return error("RECOVERY_ACTION_UNSUPPORTED", "only rollback recovery is supported")
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        transaction = session.scalar(
            select(TaskTransaction)
            .where(TaskTransaction.task_id == task_id)
            .where(
                TaskTransaction.state.in_(
                    [
                        TransactionState.PREPARED,
                        TransactionState.APPLYING,
                        TransactionState.CONFLICT,
                    ]
                )
            )
            .order_by(TaskTransaction.updated_at.desc(), TaskTransaction.id.desc())
        )
        if transaction is None:
            transaction = session.scalar(
                select(TaskTransaction)
                .where(TaskTransaction.task_id == task_id)
                .where(TaskTransaction.state == TransactionState.COMMITTED)
                .order_by(TaskTransaction.updated_at.desc(), TaskTransaction.id.desc())
            )
        if transaction is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("RECOVERY_NOT_FOUND", "recoverable transaction not found")
        project = session.get(Project, task.project_id)
        if project is None:
            response.status_code = status.HTTP_409_CONFLICT
            return error("RECOVERY_EVIDENCE_MISSING", "task project not found")
        try:
            resolution = TransactionRecoveryService(
                session,
                project_root=project.root_path,
            ).resolve_by_rollback(
                task_id=task_id,
                transaction_id=transaction.id,
            )
        except Exception as exc:
            response.status_code = status.HTTP_409_CONFLICT
            return error("RECOVERY_FAILED", str(exc))
        return ok(
            {
                "taskId": task_id,
                "transactionId": resolution.transaction_id,
                "status": "RESOLVED" if resolution.resolved else "UNCHANGED",
                "action": payload.action,
                "restoredPaths": list(resolution.rollback.restored_paths),
                "deletedPaths": list(resolution.rollback.deleted_paths),
            }
        )
