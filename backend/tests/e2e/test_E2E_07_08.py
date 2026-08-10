from __future__ import annotations

import shutil
from pathlib import Path

from phase1_test_helpers import REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.knowledge.freshness import FreshnessService, FreshnessStatus
from se_mentor.knowledge.refresh_queue import RefreshQueue
from se_mentor.knowledge.signature import KnowledgeSignatureBuilder
from se_mentor.models.execution import TaskTransaction, TransactionState, WorkspaceLockMode
from se_mentor.models.knowledge import (
    EngineeringKnowledge,
    KnowledgeSignature,
    KnowledgeStatus,
    KnowledgeType,
)
from se_mentor.transactions.manager import TransactionManager
from se_mentor.transactions.recovery import RecoveryDecision, TransactionRecoveryService
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService


def test_E2E_07_crash_recovery(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    engine = create_schema(tmp_path / "e2e07.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)
    lock_service = WorkspaceLockService(session_factory)
    acquired = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="before-crash",
        reason="crash recovery",
    )
    assert acquired.lock is not None

    with session_scope(session_factory) as session:
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=acquired.lock.id,
            expected_base_revision=REVISION,
        )
        transaction = session.get(TaskTransaction, prepared.transaction_id)
        assert transaction is not None
        transaction.state = TransactionState.APPLYING
        (repo / "external.py").write_text("changed after crash\n", encoding="utf-8")
        summaries = TransactionRecoveryService(session, project_root=repo).scan_project(
            project_id=ids["project_id"]
        )

    blocked = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=other["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="new-writer",
        reason="blocked until recovery",
    )

    assert summaries[0].decision == RecoveryDecision.MANUAL
    assert summaries[0].external_changes == ("external.py",)
    assert blocked.status == LockAcquireStatus.RECOVERY_REQUIRED

    (repo / "external.py").write_text('state = "before crash"\n', encoding="utf-8")
    with session_scope(session_factory) as session:
        resolution = TransactionRecoveryService(session, project_root=repo).resolve_by_rollback(
            task_id=ids["task_id"],
            transaction_id=prepared.transaction_id,
        )

    assert resolution.resolved is True
    released = lock_service.acquire(
        project_id=ids["project_id"],
        task_id=other["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="new-writer",
        reason="recovery complete",
    )
    assert released.status == LockAcquireStatus.ACQUIRED


def test_E2E_08_knowledge_freshness(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    engine = create_schema(tmp_path / "e2e08.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    builder = KnowledgeSignatureBuilder(repo)
    original = builder.for_file("memory.py", revision=REVISION)
    queue = RefreshQueue()

    with session_scope(session_factory) as session:
        knowledge = EngineeringKnowledge(
            project_id=ids["project_id"],
            knowledge_key="memory.message",
            knowledge_type=KnowledgeType.DECISION,
            status=KnowledgeStatus.VERIFIED,
            version=1,
            scope_json='{"path":"memory.py"}',
            summary="message returns old memory",
            verified_evidence_json='["evidence/test-reports/T084.xml"]',
        )
        session.add(knowledge)
        session.flush()
        session.add(
            KnowledgeSignature(knowledge_id=knowledge.id, signature_hash=original.signature_hash)
        )
        session.flush()
        knowledge_id = knowledge.id

    (repo / "memory.py").write_text(
        "def message() -> str:\n    return 'new memory'\n", encoding="utf-8"
    )
    current = builder.for_file("memory.py", revision=REVISION)
    with session_scope(session_factory) as session:
        result = FreshnessService(session, queue).evaluate(knowledge_id, current.signature_hash)
        stored = session.get(EngineeringKnowledge, knowledge_id)
        assert stored is not None

    assert result.status == FreshnessStatus.DRIFTED
    assert result.can_auto_allow is False
    assert stored.status == KnowledgeStatus.STALE
    assert queue.items == (knowledge_id,)


def _copy_fixture(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "fixtures" / "e2e" / "recovery_memory"
    repo = tmp_path / "repo"
    shutil.copytree(source, repo)
    return repo
