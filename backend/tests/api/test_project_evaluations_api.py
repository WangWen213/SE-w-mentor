from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from se_mentor.api.runtime import get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.evaluation.service import EvaluationService
from se_mentor.main import create_app
from se_mentor.models.evaluation import TaskEvaluation
from se_mentor.models.project import Project
from se_mentor.models.task import ChangeTask, TaskStatus


def test_project_evaluations_reads_persisted_project_projection() -> None:
    client = TestClient(create_app())
    factory = get_session_factory()
    root_token = uuid4().hex
    with session_scope(factory) as session:
        project = Project(root_path=f"C:/repo-eval-{root_token}")
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="记录完成后的评估",
            status=TaskStatus.COMPLETED,
        )
        session.add(task)
        session.flush()
        payload = EvaluationService(session).build_payload(task)
        session.add(
            TaskEvaluation(
                project_id=project.id,
                task_id=task.id,
                status="COMPLETED",
                summary_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
        )
        session.flush()
        project_id = project.id
        task_id = task.id

    response = client.get(f"/api/projects/{project_id}/evaluations")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["projectId"] == project_id
    assert [item["taskId"] for item in body["items"]] == [task_id]
