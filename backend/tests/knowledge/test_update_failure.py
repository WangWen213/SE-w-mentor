from __future__ import annotations

from se_mentor.knowledge.update_failure import FailedTaskResult, FailureKnowledgeUpdater
from se_mentor.models.knowledge import KnowledgeStatus, KnowledgeType


def test_T080_rolled_back_task_creates_failure_experience_not_verified_fact() -> None:
    updater = FailureKnowledgeUpdater()

    record = updater.extract(
        FailedTaskResult(
            task_id="task-rollback",
            outcome="ROLLED_BACK",
            attempted_paths=("backend/src/app.py",),
            failure_summary="Patch failed after rollback",
            evidence_refs=("evidence/logs/T080.log",),
            log_text="Traceback with OPENAI_API_KEY=sk-secret",
        )
    )

    assert record.status == KnowledgeStatus.FAILED_EXPERIENCE
    assert record.knowledge_type == KnowledgeType.FAILURE
    assert record.active_implementation_fact is False
    assert record.task_id == "task-rollback"
    assert "sk-secret" not in record.summary
    assert "[REDACTED:SECRET]" in record.summary
