from __future__ import annotations

from fastapi import APIRouter, Response, status

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.evaluation.service import EvaluationService
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask

router = APIRouter(tags=["evaluation"])
_SESSION_FACTORY = get_session_factory()


@router.get("/api/tasks/{task_id}/evaluation")
def task_evaluation(task_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(ChangeTask, task_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        payload = EvaluationService(session).get_task_payload(task_id)
        return ok(payload)


@router.get("/api/projects/{project_id}/evaluations")
def project_evaluations(project_id: str, response: Response) -> dict[str, object]:
    with session_scope(_SESSION_FACTORY) as session:
        if session.get(Project, project_id) is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("PROJECT_NOT_FOUND", "project not found")
        items = EvaluationService(session).list_project_payloads(project_id)
        return ok({"projectId": project_id, "items": items})
