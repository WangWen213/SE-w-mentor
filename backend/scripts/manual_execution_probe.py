from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from se_mentor.agent.runtime import RuntimePolicy
from se_mentor.api.events import BUS
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.execution.orchestrator import ExecutionOrchestrator
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.execution import FileChange, ToolExecution, WorkspaceLock
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceDecisionStatus,
    GovernanceVerdict,
)
from se_mentor.models.llm import AgentAction, AgentActionStatus, ParseStatus, RiskLevel
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskIteration,
    TaskIterationPhase,
    TaskStatus,
)

PROPOSAL_HASH = "d" * 64
REVISION = "manual-probe-revision"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a manual production harness execution probe.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary directory after the probe",
    )
    args = parser.parse_args()

    if args.keep:
        temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    else:
        temp = tempfile.TemporaryDirectory()
    with temp:
        root = Path(temp.name)
        result = run_probe(root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1


def run_probe(root: Path) -> dict[str, Any]:
    repo = root / "repo"
    repo.mkdir(parents=True)
    target = repo / "app.txt"
    target.write_text("TASK\n", encoding="utf-8", newline="\n")
    _git(repo, "init")
    _git(repo, "config", "user.email", "probe@example.com")
    _git(repo, "config", "user.name", "Manual Probe")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    engine = create_sqlite_engine(f"sqlite:///{root / 'probe.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    ids = _seed(session_factory, repo)
    provider = MockLLMProvider(
        model="manual-execution-probe",
        script=(
            MockResponse(
                match="Previous tool result",
                content=json.dumps(
                    {
                        "action_type": "APPLY_PATCH",
                        "parameters": {
                            "relative_path": "app.txt",
                            "expected_sha256": _sha(target),
                            "replacements": [{"old": "TASK\n", "new": "TASK1\n"}],
                        },
                        "reason": "Apply the confirmed TASK to TASK1 change.",
                    },
                    sort_keys=True,
                ),
                input_tokens=20,
                output_tokens=18,
            ),
            MockResponse(
                match="Change TASK to TASK1",
                content=json.dumps(
                    {
                        "action_type": "READ_FILE",
                        "parameters": {"path": "app.txt", "start_line": 1, "end_line": 20},
                        "reason": "Inspect the file before applying the confirmed change.",
                    },
                    sort_keys=True,
                ),
                input_tokens=12,
                output_tokens=12,
            ),
        ),
    )
    runtime_policy = RuntimePolicy(max_iterations=4, max_parse_failures=2, max_stalled_iterations=3)
    orchestrator = ExecutionOrchestrator(
        session_factory,
        provider_override=provider,
        runtime_policy=runtime_policy,
    )
    try:
        result = orchestrator.execute_task(ids["task_id"], command="RUN_COMMAND")

        with session_scope(session_factory) as session:
            actions = [
                {
                    "id": action.id,
                    "action_type": action.action_type,
                    "status": action.status,
                    "parameters_summary": action.parameters_summary,
                }
                for action in session.query(AgentAction)
                .order_by(AgentAction.created_at, AgentAction.id)
                .all()
            ]
            tools = [
                {
                    "id": tool.id,
                    "tool_name": tool.tool_name,
                    "status": tool.status,
                    "transaction_id": tool.transaction_id,
                }
                for tool in session.query(ToolExecution)
                .order_by(ToolExecution.created_at, ToolExecution.id)
                .all()
            ]
            changes = [
                {
                    "id": change.id,
                    "relative_path": change.relative_path,
                    "before_hash": change.before_hash,
                    "after_hash": change.after_hash,
                    "tool_execution_id": change.tool_execution_id,
                }
                for change in session.query(FileChange)
                .order_by(FileChange.created_at, FileChange.id)
                .all()
            ]
            locks = [
                {
                    "id": lock.id,
                    "mode": lock.lock_mode,
                    "status": lock.status,
                }
                for lock in session.query(WorkspaceLock)
                .order_by(WorkspaceLock.created_at, WorkspaceLock.id)
                .all()
            ]
    finally:
        engine.dispose()

    git_diff = _git(repo, "diff", "--", "app.txt")
    content = target.read_text(encoding="utf-8")
    transaction_id = next(
        (tool["transaction_id"] for tool in tools if tool["transaction_id"]), None
    )
    stage_events = [event.event_type for event in BUS.replay(task_id=ids["task_id"])]
    facts = {
        "task_id": ids["task_id"],
        "transaction_id": transaction_id,
        "execution_result": result.payload(),
        "AgentActions": actions,
        "ToolExecutions": tools,
        "FileChanges": changes,
        "workspace": {
            "repo": str(repo),
            "locks": locks,
            "app_txt": content,
        },
        "stage_ledger": stage_events,
        "git_diff": git_diff,
    }
    broken = _first_broken_stage(facts)
    return {
        "status": "FAIL" if broken else "PASS",
        "first_broken_stage": broken,
        **facts,
    }


def _seed(session_factory, repo: Path) -> dict[str, str]:
    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Change TASK to TASK1 in app.txt.",
            base_revision=REVISION,
            status=TaskStatus.ACTION_PENDING,
        )
        session.add(task)
        session.flush()
        proposal = ChangeProposal(
            task_id=task.id,
            version=1,
            goal="Change TASK to TASK1.",
            expected_behavior="app.txt contains TASK1.",
            initial_scope_json='["app.txt"]',
            acceptance_criteria_json='["app.txt contains TASK1"]',
            validation_plan_json='["git diff shows app.txt changed"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.CONFIRMED,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        session.add(proposal)
        session.flush()
        task.active_proposal_id = proposal.id
        iteration = TaskIteration(
            task_id=task.id, iteration_number=1, phase=TaskIterationPhase.ANALYZE
        )
        session.add(iteration)
        session.flush()
        governance_action = AgentAction(
            task_id=task.id,
            iteration_id=iteration.id,
            action_sequence=1,
            action_type="APPLY_PATCH",
            parameters_summary="manual probe governance seed",
            schema_version="v1",
            parse_status=ParseStatus.VALID,
            risk_level=RiskLevel.LOW,
            status=AgentActionStatus.SUCCEEDED,
            idempotency_key=f"manual-probe:{task.id}",
        )
        session.add(governance_action)
        session.flush()
        decision = GovernanceDecision(
            task_id=task.id,
            action_id=governance_action.id,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            decision=GovernanceVerdict.ALLOW,
            risk_level=RiskLevel.LOW,
            reason_summary="manual probe allowed scope",
            approval_required=False,
            status=GovernanceDecisionStatus.ACTIVE,
            rule_set_version="manual-probe",
            evidence_json="[]",
        )
        session.add(decision)
        session.flush()
        policy = ExecutionPolicy(
            task_id=task.id,
            action_id=governance_action.id,
            governance_decision_id=decision.id,
            approval_request_id=None,
            proposal_hash=PROPOSAL_HASH,
            revision=REVISION,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=True,
            read_paths_json='["app.txt"]',
            write_paths_json='["app.txt"]',
            protected_paths_json="[]",
            commands_json='["RUN_COMMAND"]',
            network_json="{}",
            resource_limits_json="{}",
            invalidation_json="{}",
            evidence_json="{}",
        )
        session.add(policy)
        session.flush()
        task.active_policy_id = policy.id
        return {"task_id": task.id}


def _first_broken_stage(facts: dict[str, Any]) -> str | None:
    stage_ledger = set(facts["stage_ledger"])
    required_stages = {
        "EXECUTION_STARTED",
        "CONTEXT_BUILT",
        "LLM_REQUESTED",
        "LLM_RESPONDED",
        "ACTION_PARSED",
        "ACTION_GOVERNED",
        "TOOL_DISPATCHED",
        "TOOL_COMPLETED",
        "FILE_CHANGED",
        "TASK_COMPLETED",
    }
    missing = sorted(required_stages - stage_ledger)
    if missing:
        return f"stage_ledger_missing:{missing[0]}"
    write_tools = [
        item
        for item in facts["ToolExecutions"]
        if item["tool_name"] == "APPLY_PATCH" and item["status"] == "SUCCEEDED"
    ]
    if not write_tools:
        return "WRITE ToolExecution"
    if not facts["FileChanges"]:
        return "FileChange"
    if not any(change["before_hash"] != change["after_hash"] for change in facts["FileChanges"]):
        return "before_hash == after_hash"
    if facts["workspace"]["app_txt"] != "TASK1\n":
        return "actual file content changed"
    if not str(facts["git_diff"]).strip():
        return "git diff non-empty"
    return None


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
