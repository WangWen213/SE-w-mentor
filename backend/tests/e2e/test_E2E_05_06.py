from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from phase1_test_helpers import PROPOSAL_HASH, REVISION, create_schema, seed_task_graph

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.agent.runtime import AgentRuntime
from se_mentor.context.context_builder import ContextBuilder
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import TaskTransaction, TransactionState, WorkspaceLockMode
from se_mentor.models.task import ChangeTask, TaskStatus
from se_mentor.policy.grants import TemporaryGrantService
from se_mentor.progress.stagnation import ActionObservation, StagnationMonitor
from se_mentor.tools.apply_patch import AtomicApplyPatchTool, StructuredPatch
from se_mentor.tools.create_file import CreateFileTool
from se_mentor.tools.registry import ToolRegistry
from se_mentor.transactions.manager import TransactionManager
from se_mentor.transactions.rollback import TransactionRollbackService
from se_mentor.workspace.lock_service import WorkspaceLockService


def test_E2E_05_stagnation(tmp_path: Path) -> None:
    _copy_fixture(tmp_path)
    engine = create_schema(tmp_path / "e2e05.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        monitor = StagnationMonitor(session, threshold=2, max_iterations=4, token_budget=100)
        first = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "app.py", False, ()),
            provider_calls=1,
            spent_tokens=10,
        )
        second = monitor.record(
            task_id=ids["task_id"],
            observation=ActionObservation("READ_FILE", "app.py", False, ()),
            provider_calls=1,
            spent_tokens=10,
        )
        task = session.get(ChangeTask, ids["task_id"])

    assert first.provider_allowed is True
    assert second.stagnated is True
    assert second.provider_allowed is False
    assert second.repeated_count == 2
    assert task is not None
    assert task.status == TaskStatus.STAGNATION_WARNING


def test_E2E_06_cancel_rollback(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    user_dirty = repo / "user_notes.txt"
    modified = repo / "src" / "modified.py"
    created = repo / "src" / "created.py"
    engine = create_schema(tmp_path / "e2e06.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    lock = WorkspaceLockService(session_factory).acquire(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        mode=WorkspaceLockMode.WRITE,
        owner_instance="e2e",
        reason="cancel rollback",
    )
    assert lock.lock is not None

    provider = MockLLMProvider(
        model="mock",
        script=(
            MockResponse(
                match="run",
                content='{"action_type":"READ_FILE","path":"src/modified.py","reason":"inspect"}',
                input_tokens=1,
                output_tokens=1,
            ),
        ),
    )
    runtime = AgentRuntime()
    child = runtime.start_process([sys.executable, "-c", "import time; time.sleep(30)"], cwd=repo)

    with session_scope(session_factory) as session:
        prepared = TransactionManager(session, backup_root=tmp_path / "backups").prepare(
            task_id=ids["task_id"],
            project_id=ids["project_id"],
            lock_id=lock.lock.id,
            expected_base_revision=REVISION,
        )
        policy = _policy(session, ids, ("src/modified.py", "src/created.py"))
        grant = TemporaryGrantService(session).create(
            policy.id,
            write_paths=("src/modified.py", "src/created.py"),
            commands=(),
        )
        AtomicApplyPatchTool(session, project_root=repo).apply(
            task_id=ids["task_id"],
            action_id=ids["action_id"],
            transaction_id=prepared.transaction_id,
            grant=grant,
            patch=StructuredPatch(
                "src/modified.py",
                _sha(modified),
                (("value = 1", "value = 2"),),
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
        runner = SingleTurnAgentRunner(
            session,
            project_root=repo,
            context_builder=ContextBuilder(max_chars=2000),
            provider=provider,
            registry=ToolRegistry(),
            tool_handlers={},
        )
        runtime = AgentRuntime(session, runner=runner)
        runtime._children.append(child)
        runtime.request_cancel(task_id=ids["task_id"], reason="user cancel")
        result = runtime.run_once(
            task_id=ids["task_id"],
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            goal="run",
        )
        terminated = runtime.terminate_children(timeout_seconds=5)
        rollback = TransactionRollbackService(session, project_root=repo).rollback(
            task_id=ids["task_id"],
            transaction_id=prepared.transaction_id,
        )
        transaction = session.get(TaskTransaction, prepared.transaction_id)

    assert result.cancelled is True
    assert provider.calls == 0
    assert terminated == 1
    assert child.poll() is not None
    assert rollback.rolled_back is True
    assert transaction is not None
    assert transaction.state == TransactionState.ROLLED_BACK
    assert modified.read_text(encoding="utf-8") == "value = 1\n"
    assert not created.exists()
    assert user_dirty.read_text(encoding="utf-8") == "user dirty before task\n"


def _copy_fixture(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "fixtures" / "e2e" / "resilience"
    repo = tmp_path / "repo"
    shutil.copytree(source, repo)
    return repo


def _policy(session, ids: dict[str, str], write_paths: tuple[str, ...]) -> ExecutionPolicy:
    policy = ExecutionPolicy(
        task_id=ids["task_id"],
        action_id=ids["action_id"],
        governance_decision_id=ids["decision_id"],
        approval_request_id=None,
        proposal_hash=PROPOSAL_HASH,
        revision=REVISION,
        status=ExecutionPolicyStatus.ACTIVE,
        executable=True,
        read_paths_json='["src/modified.py","src/created.py"]',
        write_paths_json='["src/modified.py","src/created.py"]',
        protected_paths_json="[]",
        commands_json="[]",
        network_json='{"enabled":false}',
        resource_limits_json='{"timeout_seconds":30}',
        invalidation_json="{}",
        evidence_json='[{"source":"e2e"}]',
    )
    session.add(policy)
    session.flush()
    return policy


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
