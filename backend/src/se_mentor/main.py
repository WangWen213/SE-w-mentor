from __future__ import annotations

from fastapi import FastAPI

from se_mentor.api.analysis import router as analysis_router
from se_mentor.api.approvals import router as approvals_router
from se_mentor.api.execution import router as execution_router
from se_mentor.api.governance import router as governance_router
from se_mentor.api.projects import router as projects_router
from se_mentor.api.proposals import router as proposals_router
from se_mentor.api.tasks import router as tasks_router


def create_app() -> FastAPI:
    app = FastAPI(title="SE-Mentor API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(proposals_router)
    app.include_router(analysis_router)
    app.include_router(governance_router)
    app.include_router(approvals_router)
    app.include_router(execution_router)
    return app
