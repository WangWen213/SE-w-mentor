from __future__ import annotations

from pathlib import Path

from se_mentor.knowledge.update_success import SuccessfulTaskResult, SuccessKnowledgeUpdater
from se_mentor.models.knowledge import KnowledgeStatus


def test_T079_success_knowledge_uses_committed_diff_and_passed_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "backend" / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    updater = SuccessKnowledgeUpdater(tmp_path)

    records = updater.extract(
        SuccessfulTaskResult(
            task_id="task-1",
            revision="abc123",
            committed_diff="+def answer():\n+    return 42\n",
            changed_paths=("backend/src/app.py",),
            passed_validation_refs=("evidence/test-reports/T079.xml",),
            final_summary="Implemented answer helper.",
        )
    )

    assert len(records) == 1
    record = records[0]
    assert record.status == KnowledgeStatus.VERIFIED
    assert record.task_id == "task-1"
    assert record.relative_path == "backend/src/app.py"
    assert record.signature.revision == "abc123"
    assert record.evidence_refs == ("evidence/test-reports/T079.xml",)
