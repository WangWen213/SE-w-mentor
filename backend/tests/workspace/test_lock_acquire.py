from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.execution import WorkspaceLockMode, WorkspaceLockStatus
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService


def test_AC_FR01_03_two_concurrent_writers_only_one_succeeds(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "locks.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    other_ids = seed_task_graph(engine, tmp_path / "other")
    session_factory = create_session_factory(engine)
    service = WorkspaceLockService(session_factory)

    def acquire(task_id: str) -> LockAcquireStatus:
        return service.acquire(
            project_id=ids["project_id"],
            task_id=task_id,
            mode=WorkspaceLockMode.WRITE,
            owner_instance=f"owner-{task_id}",
            reason="exclusive edit",
        ).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(acquire, [ids["task_id"], other_ids["task_id"]]))

    assert statuses.count(LockAcquireStatus.ACQUIRED) == 1
    assert statuses.count(LockAcquireStatus.CONFLICT) == 1

    with session_scope(session_factory) as session:
        active = service.acquire(
            project_id=ids["project_id"],
            task_id=ids["task_id"],
            mode=WorkspaceLockMode.READ,
            owner_instance="reader",
            reason="inspect",
            session=session,
        )
        assert active.status is LockAcquireStatus.CONFLICT
        assert active.transaction_created is False
        assert active.lock is None

    read_project = seed_task_graph(engine, tmp_path / "reads")
    first = service.acquire(
        project_id=read_project["project_id"],
        task_id=read_project["task_id"],
        mode=WorkspaceLockMode.READ,
        owner_instance="reader-1",
        reason="inspect",
    )
    second = service.acquire(
        project_id=read_project["project_id"],
        task_id=read_project["task_id"],
        mode=WorkspaceLockMode.READ,
        owner_instance="reader-2",
        reason="inspect",
    )
    assert first.status is LockAcquireStatus.ACQUIRED
    assert second.status is LockAcquireStatus.ACQUIRED
    assert first.lock is not None
    assert first.lock.status == WorkspaceLockStatus.ACTIVE
