from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import BackupEntry, FileChange, WorkspaceLockMode
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.tools.apply_patch import ApplyPatchError, AtomicApplyPatchTool, StructuredPatch
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_T059_hash_conflict_and_pre_replace_crash_preserve_original_file(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "apply-patch.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="agent-1",
        reason="apply patch",
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
            read_paths_json='["app.py"]',
            write_paths_json='["app.py"]',
            protected_paths_json='[".env"]',
            commands_json='["pytest"]',
            network_json='{"enabled":false}',
            resource_limits_json='{"timeout_seconds":30}',
            invalidation_json='{"proposal_hash":"aaaaaaaa"}',
            evidence_json='[{"source":"test"}]',
        )
        session.add(policy)
        session.flush()
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("app.py",),
            commands=(),
        )
        tool = AtomicApplyPatchTool(session, project_root=repo)
        first_hash = _sha(target.read_bytes())
        result = tool.apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch(
                relative_path="app.py",
                expected_sha256=first_hash,
                replacements=(("value = 1", "value = 2"),),
            ),
            revision=REVISION,
        )

        with pytest.raises(ApplyPatchError, match="expected hash"):
            tool.apply(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                patch=StructuredPatch(
                    relative_path="app.py",
                    expected_sha256=first_hash,
                    replacements=(("value = 2", "value = 3"),),
                ),
                revision=REVISION,
            )
        crash_hash = _sha(target.read_bytes())
        with pytest.raises(ApplyPatchError, match="pre_replace_crash"):
            tool.apply(
                task_id=ids["task_id"],
                action_id=ids["action_id"],
                transaction_id=prepared.transaction_id,
                grant=grant,
                patch=StructuredPatch(
                    relative_path="app.py",
                    expected_sha256=crash_hash,
                    replacements=(("value = 2", "value = 4"),),
                ),
                revision=REVISION,
                simulate_crash_before_replace=True,
            )
        assert session.query(BackupEntry).count() == 1
        assert session.query(FileChange).count() == 1

    assert result.relative_path == "app.py"
    assert result.before_sha256 == first_hash
    assert "-value = 1" in result.diff
    assert "+value = 2" in result.diff
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
