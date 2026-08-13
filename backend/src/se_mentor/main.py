from __future__ import annotations

import logging

from fastapi import FastAPI

from se_mentor.api.analysis import router as analysis_router
from se_mentor.api.approvals import router as approvals_router
from se_mentor.api.approvals import set_session_factory as set_approval_session_factory
from se_mentor.api.audit import router as audit_router
from se_mentor.api.credentials import router as credentials_router
from se_mentor.api.diffs import router as diffs_router
from se_mentor.api.evaluation import router as evaluation_router
from se_mentor.api.events import router as events_router
from se_mentor.api.execution import router as execution_router
from se_mentor.api.execution import (
    set_execution_authority_dependencies,
)
from se_mentor.api.governance import router as governance_router
from se_mentor.api.governance_history import router as governance_history_router
from se_mentor.api.memory import router as memory_router
from se_mentor.api.mentor_turns import router as mentor_turns_router
from se_mentor.api.projects import router as projects_router
from se_mentor.api.proposals import router as proposals_router
from se_mentor.api.recovery import router as recovery_router
from se_mentor.api.replay import router as replay_router
from se_mentor.api.runtime import get_runtime_settings, get_session_factory
from se_mentor.api.tasks import router as tasks_router
from se_mentor.api.workbench_messages import router as workbench_messages_router
from se_mentor.observability.logging import configure_runtime_logging

LOGGER = logging.getLogger("se_mentor.main")


def create_app() -> FastAPI:
    configure_runtime_logging(get_runtime_settings().runtime_root)
    LOGGER.info("runtime_profile=%s", get_runtime_settings().profile.value)
    app = FastAPI(title="SE-Mentor API", version="0.1.0")
    session_factory = get_session_factory()
    set_approval_session_factory(session_factory)
    set_execution_authority_dependencies(session_factory=session_factory, reset_orchestrator=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects_router)
    app.include_router(credentials_router)
    app.include_router(tasks_router)
    app.include_router(mentor_turns_router)
    app.include_router(workbench_messages_router)
    app.include_router(proposals_router)
    app.include_router(analysis_router)
    app.include_router(governance_router)
    app.include_router(governance_history_router)
    app.include_router(memory_router)
    app.include_router(approvals_router)
    app.include_router(execution_router)
    app.include_router(evaluation_router)
    app.include_router(recovery_router)
    app.include_router(events_router)
    app.include_router(audit_router)
    app.include_router(diffs_router)
    app.include_router(replay_router)
    return app
