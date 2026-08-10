from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import TaskTransaction, TransactionState, WorkspaceLockMode
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.apply_patch import AtomicApplyPatchTool, StructuredPatch
from se_mentor.tools.create_file import CreateFileTool
from se_mentor.tools.delete_file import DeleteFileTool
from se_mentor.transactions.manager import TransactionManager
from se_mentor.transactions.rollback import RollbackConflict, TransactionRollbackService
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_AC_FR07_10_rollback_preserves_existing_changes(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "rollback.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    user_existing = repo / "user_notes.txt"
    modified = repo / "src" / "modified.py"
    deleted = repo / "src" / "deleted.py"
    created = repo / "src" / "created.py"
    user_existing.write_text("user dirty before task\n", encoding="utf-8")
    modified.write_text("value = 1\n", encoding="utf-8")
    deleted.write_text("remove me\n", encoding="utf-8")
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="rollback",
    )
    assert lock.lock is not None

    with session_scope(session_factory) as session:
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
        )
        policy = ExecutionPolicy(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            governance_decision_id=ids["decision_id"],
            approval_request_id=None,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["src/modified.py","src/deleted.py","src/created.py"]',
            write_paths_json='["src/modified.py","src/deleted.py","src/created.py"]',
            protected_paths_json='[".env"]',
            commands_json="[]",
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":30}',
            invalidation_json='{"proposal_hash":"aaaaaaaa"}',
            evidence_json='[{"source":"test"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("src/modified.py", "src/deleted.py", "src/created.py"),
            commands=(),
        )
        AtomicApplyPatchTool(session, project_root=repo).apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch(
                relative_path="src/modified.py",
                expected_sha256=_sha(modified.read_bytes()),
                replacements=(("value = 1", "value = 2"),),
            ),
            revision=REVISION,
        )
        CreateFileTool(session, project_root=repo).create(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            relative_path="src/created.py",
            content="created = True\n",
            revision=REVISION,
        )
        DeleteFileTool(session, project_root=repo).delete(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            relative_path="src/deleted.py",
            revision=REVISION,
        )
        service = TransactionRollbackService(session, project_root=repo)
        modified.write_text("external edit\n", encoding="utf-8")
        with pytest.raises(RollbackConflict, match="current hash"):
            service.rollback(task_id=ids["task_id"], transaction_id=prepared.transaction_id)
        assert modified.read_text(encoding="utf-8") == "external edit\n"
        assert (
            session.get(TaskTransaction, prepared.transaction_id).state == TransactionState.CONFLICT
        )

        modified.write_text("value = 2\n", encoding="utf-8")
        result = service.rollback(task_id=ids["task_id"], transaction_id=prepared.transaction_id)
        repeated = service.rollback(task_id=ids["task_id"], transaction_id=prepared.transaction_id)
        transaction = session.get(TaskTransaction, prepared.transaction_id)

    assert result.rolled_back is True
    assert repeated.rolled_back is False
    assert transaction.state == TransactionState.ROLLED_BACK
    assert user_existing.read_text(encoding="utf-8") == "user dirty before task\n"
    assert modified.read_text(encoding="utf-8") == "value = 1\n"
    assert deleted.read_text(encoding="utf-8") == "remove me\n"
    assert not created.exists()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
