from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from se_mentor.api.envelope import error, ok
from se_mentor.api.online_access import require_proposal_access, require_task_access
from se_mentor.api.proposals import _proposal_payload
from se_mentor.api.runtime import get_session_factory
from se_mentor.api.workbench_presentation import workbench_message_text
from se_mentor.db.session import session_scope
from se_mentor.models.task import ChangeProposal
from se_mentor.models.workbench import WorkbenchMessage

router = APIRouter(prefix="/api/tasks/{task_id}/messages", tags=["workbench-messages"])
_SESSION_FACTORY = get_session_factory()


class WorkbenchMessageCreate(BaseModel):
    kind: str
    proposal_id: str | None = Field(default=None, alias="proposalId")
    role: str
    status: str
    text: str


@router.get("")
def list_messages(task_id: str, request: Request, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        items = session.scalars(
            select(WorkbenchMessage)
            .where(WorkbenchMessage.task_id == task_id)
            .order_by(WorkbenchMessage.sequence.asc(), WorkbenchMessage.id.asc())
        ).all()
        return ok({"taskId": task_id, "items": [_message_payload(session, item) for item in items]})


@router.post("", status_code=status.HTTP_201_CREATED)
def create_message(
    task_id: str,
    payload: WorkbenchMessageCreate,
    request: Request,
    response: Response,
) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        task = require_task_access(session, task_id, request, response)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        text = payload.text.strip()
        if not text:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return error("WORKBENCH_MESSAGE_TEXT_REQUIRED", "message text is required")
        proposal_id = payload.proposal_id
        if proposal_id is not None:
            proposal = require_proposal_access(session, proposal_id, request, response)
            if proposal is None or proposal.task_id != task_id:
                response.status_code = status.HTTP_404_NOT_FOUND
                return error("PROPOSAL_NOT_FOUND", "proposal not found")
        sequence = int(
            session.scalar(
                select(func.coalesce(func.max(WorkbenchMessage.sequence), 0))
                .where(WorkbenchMessage.task_id == task_id)
            )
            or 0
        ) + 1
        message = WorkbenchMessage(
            task_id=task_id,
            sequence=sequence,
            role=payload.role,
            kind=payload.kind,
            status=payload.status,
            text=workbench_message_text(role=payload.role, kind=payload.kind, text=text),
            proposal_id=proposal_id,
        )
        session.add(message)
        session.flush()
        return ok(_message_payload(session, message))


def _message_payload(session, message: WorkbenchMessage) -> dict[str, object]:
    proposal_payload = None
    if message.proposal_id:
        proposal = session.get(ChangeProposal, message.proposal_id)
        if proposal is not None:
            proposal_payload = _proposal_payload(proposal)
    return {
        "createdAt": message.created_at.isoformat(),
        "id": message.id,
        "kind": message.kind,
        "proposal": proposal_payload,
        "role": message.role,
        "sequence": message.sequence,
        "status": message.status,
        "taskId": message.task_id,
        "text": message.text,
    }
