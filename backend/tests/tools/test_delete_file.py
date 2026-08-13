from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import BackupEntry, FileChange, FileChangeType, WorkspaceLockMode
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.delete_file import DeleteFileError, DeleteFileTool
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_T061_delete_without_matching_grant_is_blocked_and_file_unchanged(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "delete-file.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    target = repo / "src" / "delete_me.py"
    target.write_text("remove me\n", encoding="utf-8")
    other = repo / "src" / "other.py"
    other.write_text("keep me\n", encoding="utf-8")
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="delete file",
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
            read_paths_json='["src/delete_me.py"]',
            write_paths_json='["src/delete_me.py"]',
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
            write_paths=("src/delete_me.py",),
            commands=(),
        )
        tool = DeleteFileTool(session, project_root=repo)
        with pytest.raises(DeleteFileError, match="matching grant"):
            tool.delete(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                relative_path="src/other.py",
                revision=REVISION,
            )
        result = tool.delete(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            relative_path="src/delete_me.py",
            revision=REVISION,
        )
        backup = session.query(BackupEntry).one()
        change = session.query(FileChange).one()

    assert other.read_text(encoding="utf-8") == "keep me\n"
    assert not target.exists()
    assert result.deleted is True
    assert Path(backup.backup_artifact_ref).read_text(encoding="utf-8") == "remove me\n"
    assert change.change_type == FileChangeType.DELETE
    assert change.before_hash == result.before_sha256
    assert change.after_hash is None
