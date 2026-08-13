from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.agent.runtime import AgentRuntime, RuntimePolicy
from se_mentor.api.events import BUS
from se_mentor.api.runtime import get_domain_provider
from se_mentor.context.context_builder import ContextBuilder
from se_mentor.db.session import session_scope
from se_mentor.evaluation.service import EvaluationService
from se_mentor.llm.base import LLMProvider
from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.models.code_index import CodeIndex, CodeIndexStatus, CodeSymbol
from se_mentor.models.execution import (
    FileChange,
    TaskTransaction,
    TransactionState,
    WorkspaceLockMode,
    WorkspaceLockStatus,
)
from se_mentor.models.task import ChangeProposal, ChangeTask, TaskStatus
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import ExecutionAuthorization
from se_mentor.tools.apply_patch import AtomicApplyPatchTool, StructuredPatch
from se_mentor.tools.create_file import CreateFileTool
from se_mentor.tools.delete_file import DeleteFileTool
from se_mentor.tools.registry import ToolRegistry, ToolSpec
from se_mentor.tools.shell import ShellTool
from se_mentor.transactions.manager import TransactionManager
from se_mentor.workspace.lock_service import LockAcquireStatus, WorkspaceLockService

LOGGER = logging.getLogger("se_mentor.execution.orchestrator")
SEARCH_CODE_MAX_FILES = 4000
SEARCH_CODE_MAX_BYTES = 512_000
SEARCH_CODE_MAX_MATCHES = 25
SEARCH_CODE_INDEX_LIMIT = 30
SEARCH_CODE_MAX_CANDIDATE_FILES = 1000
SEARCH_CODE_MAX_TOTAL_BYTES = 2_000_000
SEARCH_CODE_BOUNDED_FALLBACK_DIRS = (
    "frontend/src",
    "backend/src",
    "src",
    "app",
    "lib",
    "components",
    "pages",
    "docs",
)
SEARCH_CODE_EXCLUDED_DIRS = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".sementor",
    ".tmp",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "evidence",
    "node_modules",
}


class ExecutionOrchestratorProtocol(Protocol):
    def execute_task(self, task_id: str, *, command: str) -> ExecutionResult: ...

    def cancel_task(self, task_id: str) -> ExecutionResult: ...


@dataclass(frozen=True)
class ExecutionResult:
    task_id: str
    status: str
    event_id: int
    command: str | None = None
    lock_id: str | None = None
    policy_id: str | None = None
    code: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            key: value
            for key, value in {
                "taskId": self.task_id,
                "command": self.command,
                "status": self.status,
                "eventId": self.event_id,
                "lockId": self.lock_id,
                "policyId": self.policy_id,
                "code": self.code,
                "error": self.error,
            }.items()
            if value is not None
        }


class ExecutionOrchestrator:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        runtime: AgentRuntime | None = None,
        provider_override: LLMProvider | None = None,
        runtime_policy: RuntimePolicy | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.runtime = runtime
        self.provider_override = provider_override
        self.runtime_policy = runtime_policy

    def execute_task(self, task_id: str, *, command: str) -> ExecutionResult:
        total_started = perf_counter()
        with session_scope(self.session_factory) as session:
            prepare_started = perf_counter()
            task = session.get(ChangeTask, task_id)
            if task is None:
                raise ExecutionRejected("TASK_NOT_FOUND", "task not found")
            self._validate_executable(task)
            policy = _active_policy(session, task)
            if policy is None or not policy.executable:
                raise ExecutionRejected(
                    "EXECUTION_REJECTED", "explicit approval required before execution"
                )
            commands = _json_tuple(policy.commands_json)
            if command not in commands:
                raise ExecutionRejected("EXECUTION_REJECTED", "command outside execution policy")
            policy_ms = int((perf_counter() - prepare_started) * 1000)
            LOGGER.info(
                (
                    "[perf] execution.startup.policy task_id=%s project_id=%s "
                    "duration_ms=%s commands_count=%s"
                ),
                task_id,
                task.project_id,
                policy_ms,
                len(commands),
            )

            task.active_policy_id = policy.id
            self._stage(
                task,
                None,
                "EXECUTION_STARTED",
                "PREPARING",
                "preparing confirmed proposal execution",
            )
            authorization = ExecutionAuthorization.from_policy(policy)
            write_context = LazyWriteContext(
                session_factory=self.session_factory,
                session=session,
                task=task,
                authorization=authorization,
            )
            prepare_ms = int((perf_counter() - prepare_started) * 1000)
            LOGGER.info(
                (
                    "[perf] execution.startup.prepare task_id=%s project_id=%s "
                    "duration_ms=%s"
                ),
                task_id,
                task.project_id,
                prepare_ms,
            )
            context_started = perf_counter()
            runtime = self.runtime or self._runtime_for(
                session, task, authorization=authorization, write_context=write_context
            )
            initial_context_ms = int((perf_counter() - context_started) * 1000)
            LOGGER.info(
                (
                    "[perf] execution.startup.context task_id=%s project_id=%s "
                    "duration_ms=%s"
                ),
                task_id,
                task.project_id,
                initial_context_ms,
            )
            LOGGER.info(
                (
                    "[perf] execution.startup.total task_id=%s project_id=%s "
                    "duration_ms=%s policy_ms=%s prepare_ms=%s context_ms=%s"
                ),
                task_id,
                task.project_id,
                int((perf_counter() - total_started) * 1000),
                policy_ms,
                prepare_ms,
                initial_context_ms,
            )
            LOGGER.info(
                (
                    "[perf] execution-start task_id=%s prepare_ms=%s "
                    "initial_context_ms=%s total_ms=%s"
                ),
                task_id,
                prepare_ms,
                initial_context_ms,
                int((perf_counter() - total_started) * 1000),
            )
            event = BUS.publish(
                task_id=task_id,
                event_type="EXECUTION_STARTED",
                payload={
                    "projectId": task.project_id,
                    "taskId": task_id,
                    "state": "EXECUTING",
                    "message": "execution started",
                },
            )
            try:
                task.status = TaskStatus.EXECUTING
                runtime_started = perf_counter()
                runtime.run_task(
                    task_id=task.id,
                    proposal_hash=authorization.proposal_hash,
                    revision=authorization.revision,
                    goal=_execution_goal(task, policy, command),
                    transaction_id=lambda: write_context.transaction_id,
                    publish_stage=lambda stage, result, detail=None: self._stage(
                        task,
                        _latest_iteration_id(session, task.id),
                        stage,
                        result,
                        detail,
                    ),
                )
                LOGGER.info(
                    "[perf] execution.runtime.total task_id=%s duration_ms=%s",
                    task.id,
                    int((perf_counter() - runtime_started) * 1000),
                )
                _publish_action_events(session, task.id, write_context.transaction_id)
                changed_paths = _changed_paths(session, task.id, write_context.transaction_id)
                if not changed_paths:
                    raise CompletionInvariantViolation(
                        "execution completed without real file changes"
                    )
                _publish_file_change_events(session, task.id, write_context.transaction_id)
                transaction = (
                    session.get(TaskTransaction, write_context.transaction_id)
                    if write_context.transaction_id
                    else None
                )
                if transaction is not None:
                    transaction.state = TransactionState.COMMITTED
                    session.flush()
                write_context.release_lock()
                task.status = TaskStatus.COMPLETED
                self._stage(
                    task,
                    _latest_iteration_id(session, task.id),
                    "TASK_COMPLETED",
                    "COMPLETED",
                    ",".join(changed_paths),
                )
                BUS.publish(
                    task_id=task_id,
                    event_type="EXECUTION_COMPLETED",
                    payload={
                        "projectId": task.project_id,
                        "taskId": task_id,
                        "state": "COMPLETED",
                        "message": f"changed files: {', '.join(changed_paths)}",
                    },
                )
                try:
                    EvaluationService(session).persist_for_task(task.id)
                except Exception:
                    LOGGER.exception(
                        "TASK_EVALUATION_POSTPROCESS_FAILED task_id=%s", task.id
                    )
            except Exception as exc:
                _mark_execution_failed(session, task, write_context.transaction_id, exc)
                write_context.release_lock()
                self._stage(
                    task,
                    _latest_iteration_id(session, task.id),
                    "TASK_FAILED",
                    getattr(exc, "code", "EXECUTION_FAILED"),
                    _safe_error(exc),
                )
                failure_event = BUS.publish(
                    task_id=task_id,
                    event_type="EXECUTION_FAILED",
                    payload={
                        "projectId": task.project_id,
                        "taskId": task_id,
                        "state": "FAILED",
                        "message": _safe_error(exc),
                    },
                )
                return ExecutionResult(
                    task_id=task_id,
                    command=command,
                    status="FAILED",
                    event_id=failure_event.event_id,
                    lock_id=write_context.lock_id,
                    policy_id=policy.id,
                    code=getattr(exc, "code", "EXECUTION_FAILED"),
                    error=_safe_error(exc),
                )
            return ExecutionResult(
                task_id=task_id,
                command=command,
                status="COMPLETED",
                event_id=event.event_id,
                lock_id=write_context.lock_id,
                policy_id=policy.id,
            )

    def cancel_task(self, task_id: str) -> ExecutionResult:
        runtime = self.runtime or AgentRuntime()
        runtime.request_cancel(task_id=task_id, reason="user requested cancellation")
        event = BUS.publish(
            task_id=task_id,
            event_type="CANCEL_REQUESTED",
            payload={
                "taskId": task_id,
                "state": "CANCEL_REQUESTED",
                "message": "cancel requested",
            },
        )
        return ExecutionResult(task_id=task_id, status="CANCEL_REQUESTED", event_id=event.event_id)

    def _validate_executable(self, task: ChangeTask) -> None:
        if task.status == TaskStatus.BLOCKED:
            raise ExecutionRejected("TASK_BLOCKED", "blocked tasks cannot execute tools")

    def _runtime_for(
        self,
        session: Session,
        task: ChangeTask,
        *,
        authorization: ExecutionAuthorization,
        write_context: LazyWriteContext,
    ) -> AgentRuntime:
        registry = ToolRegistry()
        for name in (
            "READ_FILE",
            "SEARCH_CODE",
            "APPLY_PATCH",
            "CREATE_FILE",
            "DELETE_FILE",
            "RUN_COMMAND",
        ):
            registry.register(ToolSpec(name=name, risk="domain-policy", timeout_seconds=30))
        project_root = Path(task.project.root_path).resolve()
        read_cache: dict[tuple[str, int, int, str], dict[str, object]] = {}
        search_cache: dict[tuple[str, str], dict[str, object]] = {}

        def current_authorization() -> ExecutionAuthorization:
            return _current_authorization(session, task, fallback=authorization)

        runner = SingleTurnAgentRunner(
            session,
            project_root=project_root,
            context_builder=ContextBuilder(max_chars=16000),
            provider=self.provider_override or get_domain_provider(),
            registry=registry,
            tool_handlers={
                "READ_FILE": lambda action: _read_file(
                    project_root,
                    action.parameters.path,
                    start_line=action.parameters.start_line,
                    end_line=action.parameters.end_line,
                    cache=read_cache,
                ),
                "SEARCH_CODE": lambda action: _search_code(
                    session,
                    task,
                    project_root,
                    action.parameters.query,
                    revision=current_authorization().revision,
                    cache=search_cache,
                ),
                "APPLY_PATCH": lambda action: _apply_patch_action(
                    session, task, write_context, current_authorization(), action
                ),
                "CREATE_FILE": lambda action: CreateFileTool(
                    session, project_root=project_root
                ).create(
                    task_id=task.id,
                    action_id=_current_action_id(session, task.id),
                    transaction_id=write_context.ensure_prepared().transaction_id,
                    grant=current_authorization(),
                    relative_path=action.parameters.path,
                    content=action.parameters.content,
                    revision=current_authorization().revision,
                ),
                "DELETE_FILE": lambda action: DeleteFileTool(
                    session, project_root=project_root
                ).delete(
                    task_id=task.id,
                    action_id=_current_action_id(session, task.id),
                    transaction_id=write_context.ensure_prepared().transaction_id,
                    grant=current_authorization(),
                    relative_path=action.parameters.path,
                    revision=current_authorization().revision,
                ),
                "RUN_COMMAND": lambda action: ShellTool(
                    session,
                    project_root=project_root,
                    parent_env=dict(os.environ),
                ).run(
                    task_id=task.id,
                    action_id=_current_action_id(session, task.id),
                    transaction_id=None,
                    grant=current_authorization(),
                    program=action.parameters.program,
                    args=tuple(action.parameters.args),
                    cwd=".",
                    revision=current_authorization().revision,
                ),
            },
            enforcers={
                "APPLY_PATCH": lambda action: _policy_allows_write(
                    session,
                    current_authorization(),
                    action.parameters,
                    revision=current_authorization().revision,
                ),
                "CREATE_FILE": lambda action: _policy_allows_path(
                    session,
                    current_authorization(),
                    action.parameters.path,
                    revision=current_authorization().revision,
                ),
                "DELETE_FILE": lambda action: _policy_allows_path(
                    session,
                    current_authorization(),
                    action.parameters.path,
                    revision=current_authorization().revision,
                ),
            },
        )
        return AgentRuntime(session, runner=runner, policy=self.runtime_policy)

    def _stage(
        self,
        task: ChangeTask,
        iteration_id: str | None,
        stage: str,
        result: str,
        detail: str | None,
    ) -> None:
        BUS.publish(
            task_id=task.id,
            event_type=stage,
            payload={
                "taskId": task.id,
                "projectId": task.project_id,
                "iterationId": iteration_id,
                "stage": stage,
                "state": result,
                "message": detail or stage,
            },
        )


class ExecutionRejected(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CompletionInvariantViolation(RuntimeError):
    code = "NO_CODE_CHANGE_PRODUCED"


class LazyWriteContext:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        session: Session,
        task: ChangeTask,
        authorization: ExecutionAuthorization,
    ) -> None:
        self.session_factory = session_factory
        self.session = session
        self.task = task
        self.authorization = authorization
        self.lock_id: str | None = None
        self.transaction_id: str | None = None

    def ensure_prepared(self):
        if self.transaction_id is not None:
            transaction = self.session.get(TaskTransaction, self.transaction_id)
            if transaction is None:
                raise ExecutionRejected("TRANSACTION_NOT_FOUND", "prepared transaction not found")
            return transaction
        lock_result = WorkspaceLockService(self.session_factory).acquire(
            project_id=self.task.project_id,
            task_id=self.task.id,
            mode=WorkspaceLockMode.WRITE,
            owner_instance="execution-orchestrator",
            reason="execute write action",
            session=self.session,
        )
        if lock_result.status != LockAcquireStatus.ACQUIRED or lock_result.lock is None:
            raise ExecutionRejected("LOCK_CONFLICT", str(lock_result.status))
        self.lock_id = lock_result.lock.id
        self.task.workspace_lock_id = lock_result.lock.id
        prepared = TransactionManager(self.session).prepare(
            task_id=self.task.id,
            project_id=self.task.project_id,
            lock_id=lock_result.lock.id,
            expected_base_revision=self.authorization.revision,
        )
        self.transaction_id = prepared.transaction_id
        return self.session.get(TaskTransaction, prepared.transaction_id)

    def release_lock(self) -> None:
        if self.lock_id is not None:
            _release_lock(self.session, self.lock_id)


def _execution_goal(task: ChangeTask, policy: ExecutionPolicy, command: str) -> str:
    proposal = _active_proposal(task)
    write_path_items = _json_tuple(policy.write_paths_json)
    write_paths = ", ".join(write_path_items) or "no initial write hints"
    proposal_scope = (
        ", ".join(_json_tuple(proposal.initial_scope_json)) if proposal else write_paths
    )
    return (
        "Return exactly one valid AgentAction JSON object.\n"
        "The discriminator field is action_type and enum values must exactly match the schema.\n"
        "Every action MUST contain action_type, parameters, and reason.\n"
        "You are executing an already confirmed coding change. Investigation is not the endpoint.\n"
        "If the relevant file is not certain, use SEARCH_CODE/READ_FILE to gather evidence. "
        "Once the exact edit is known and policy permits it, use APPLY_PATCH for existing files.\n"
        "Do not modify the first literal text match. When the user describes a UI location, "
        "component, module, route, behavior, or structural role, verify the selected code "
        "location corresponds to that description using repository evidence.\n"
        "If multiple literal matches exist, inspect enough candidates to distinguish them. "
        "Before WRITE, make sure the chosen target is supported by the semantic description, "
        "not only by matching text. Include target_evidence in APPLY_PATCH when alternatives "
        "were seen.\n"
        "For APPLY_PATCH replacements, old text must be copied exactly from current source "
        "evidence. Preserve literal source spelling, including indentation, quotes, and "
        "unicode escape sequences such as \\u4efb\\u52a1; do not substitute the rendered "
        "UI text if the file stores an escaped string.\n"
        "When SEARCH_CODE returns multiple candidates, prefer files under frontend/src/pages, "
        "frontend/src/app, or frontend/src/components that directly match the UI text. "
        "Do not choose backend/docs/tests matches for a frontend label change unless no "
        "frontend source match exists.\n"
        "The confirmed proposal scope and initial write hints are planning evidence, not a "
        "semantic override. If SEARCH_CODE or READ_FILE proves the requested UI target lives in "
        "a different frontend source file, choose that proven file for APPLY_PATCH instead of "
        "looping on the initial proposal path. Execution-time governance will recompile an "
        "action-scoped policy for the concrete WRITE target before dispatch, and the dispatcher "
        "will still enforce the final policy decision.\n"
        "Do not use RUN_COMMAND to edit files. RUN_COMMAND is only for validation "
        "or read-only inspection; "
        "sed/perl/python rewrite commands are not acceptable write actions.\n"
        "A coding task is incomplete until FileChange exists.\n"
        'Schema-correct READ_FILE example: {"action_type":"READ_FILE","parameters":{"path":'
        '"frontend/src/app/App.tsx","start_line":1,"end_line":200},'
        '"reason":"Need to inspect the current implementation before editing it."}.\n'
        'Schema-correct APPLY_PATCH example: {"action_type":"APPLY_PATCH","parameters":'
        '{"relative_path":"frontend/src/app/App.tsx","expected_sha256":null,'
        '"replacements":[{"old":"old text","new":"new text"}],'
        '"target_evidence":{"selected_path":"frontend/src/app/App.tsx",'
        '"selection_reason":"The selected code location matches the user-described UI role."}},'
        '"reason":"Apply the confirmed text replacement in the existing file."}.\n'
        f"Task request: {task.original_request}\n"
        f"Confirmed proposal: {proposal.goal if proposal else task.original_request}\n"
        f"Confirmed proposal scope hint: {proposal_scope}\n"
        "requires_code_change=true\n"
        f"Initial write path hints: {write_paths}\n"
        "changed_files=[]\n"
        "write_tool_executions=0\n"
        f"Execution command: {command}"
    )


def _active_proposal(task: ChangeTask) -> ChangeProposal | None:
    if task.active_proposal_id:
        for proposal in task.proposals:
            if proposal.id == task.active_proposal_id:
                return proposal
    return task.proposals[-1] if task.proposals else None


def _read_file(
    project_root: Path,
    relative_path: str,
    *,
    start_line: int,
    end_line: int,
    cache: dict[tuple[str, int, int, str], dict[str, object]] | None = None,
) -> dict[str, object]:
    started = perf_counter()
    target = (project_root / relative_path).resolve()
    if not target.is_relative_to(project_root) or not target.is_file():
        raise ValueError("target path invalid")
    if start_line < 1 or end_line < start_line:
        raise ValueError("line range invalid")
    digest = _file_sha(project_root, relative_path)
    cache_key = (relative_path, start_line, end_line, digest)
    if cache is not None and cache_key in cache:
        result = dict(cache[cache_key])
        result["cache"] = "hit"
        LOGGER.info(
            "[perf] tool.read_file total_ms=%s cache=hit path=%s range=%s-%s bytes=%s",
            int((perf_counter() - started) * 1000),
            relative_path,
            start_line,
            end_line,
            len(str(result.get("excerpt", ""))),
        )
        return result
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    selected = "".join(lines[start_line - 1 : end_line])
    excerpt = selected[:2500]
    result = {
        "path": relative_path,
        "start_line": start_line,
        "end_line": min(end_line, len(lines)),
        "content": excerpt,
        "excerpt": excerpt,
        "truncated": len(selected) > len(excerpt),
        "sha256": digest,
        "cache": "miss",
    }
    if cache is not None:
        cache[cache_key] = result
    LOGGER.info(
        "[perf] tool.read_file total_ms=%s cache=miss path=%s range=%s-%s bytes=%s",
        int((perf_counter() - started) * 1000),
        relative_path,
        start_line,
        end_line,
        len(excerpt),
    )
    return result


def _search_code(
    session: Session,
    task: ChangeTask,
    project_root: Path,
    query: str,
    *,
    revision: str,
    cache: dict[tuple[str, str], dict[str, object]] | None = None,
) -> dict[str, object]:
    started = perf_counter()
    cache_key = (revision, query)
    if cache is not None and cache_key in cache:
        result = dict(cache[cache_key])
        result["cache"] = "hit"
        LOGGER.info(
            "[perf] tool.search_code total_ms=%s source=cache matches=%s query_chars=%s",
            int((perf_counter() - started) * 1000),
            result.get("total_matches", 0),
            len(query),
        )
        return result
    indexed = _search_code_index(session, task, query, revision=revision)
    if indexed:
        result = {
            "query": query,
            "matches": indexed[:5],
            "total_matches": len(indexed),
            "source": "code_index",
            "cache": "miss",
        }
        if cache is not None:
            cache[cache_key] = result
        LOGGER.info(
            "[perf] tool.search_code total_ms=%s source=code_index matches=%s query_chars=%s",
            int((perf_counter() - started) * 1000),
            len(indexed),
            len(query),
        )
        return result
    query_terms = _semantic_terms(query)
    query_variants = _text_variants(query)
    candidates, candidate_source, skipped_files = _search_code_candidate_paths(
        session, task, project_root
    )
    matches, scanned_files, read_files, bytes_read, early_stop = _search_candidate_files(
        project_root=project_root,
        candidate_paths=candidates,
        query_terms=query_terms,
        query_variants=query_variants,
        skipped_files=skipped_files,
    )
    LOGGER.info(
        (
            "[perf] tool.search_code total_ms=%s source=%s scanned_files=%s "
            "skipped_files=%s matches=%s query_chars=%s candidate_files=%s "
            "files_read=%s bytes_read=%s early_stop=%s"
        ),
        int((perf_counter() - started) * 1000),
        candidate_source,
        scanned_files,
        skipped_files,
        len(matches),
        len(query),
        len(candidates),
        read_files,
        bytes_read,
        early_stop,
    )
    result = {
        "query": query,
        "matches": matches[:5],
        "total_matches": len(matches),
        "source": candidate_source,
        "cache": "miss",
    }
    if cache is not None:
        cache[cache_key] = result
    return result


def _search_code_candidate_paths(
    session: Session,
    task: ChangeTask,
    project_root: Path,
) -> tuple[tuple[str, ...], str, int]:
    tracked = _git_tracked_paths(project_root)
    if tracked:
        paths = _merge_candidate_paths(
            tracked, _changed_paths(session, task.id, transaction_id=None)
        )
        return paths, "tracked_files", 0
    return _bounded_worktree_paths(project_root), "filesystem_bounded", 0


def _git_tracked_paths(project_root: Path) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=project_root,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode != 0:
        return ()
    paths = tuple(
        item.replace("\\", "/")
        for item in result.stdout.decode("utf-8", errors="ignore").split("\0")
        if item
    )
    return tuple(path for path in paths if not _search_path_excluded(path))[
        :SEARCH_CODE_MAX_CANDIDATE_FILES
    ]


def _merge_candidate_paths(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for path in group:
            normalized = Path(path).as_posix()
            if normalized in seen or _search_path_excluded(normalized):
                continue
            seen.add(normalized)
            merged.append(normalized)
            if len(merged) >= SEARCH_CODE_MAX_CANDIDATE_FILES:
                return tuple(merged)
    return tuple(merged)


def _bounded_worktree_paths(project_root: Path) -> tuple[str, ...]:
    paths: list[str] = []
    seen: set[str] = set()
    for relative_root in SEARCH_CODE_BOUNDED_FALLBACK_DIRS:
        root = project_root / relative_root
        if not root.exists() or not root.is_dir():
            continue
        for current, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name not in SEARCH_CODE_EXCLUDED_DIRS)
            for filename in sorted(filenames):
                path = Path(current) / filename
                try:
                    relative = path.relative_to(project_root).as_posix()
                except ValueError:
                    continue
                if relative in seen or _search_path_excluded(relative):
                    continue
                seen.add(relative)
                paths.append(relative)
                if len(paths) >= SEARCH_CODE_MAX_CANDIDATE_FILES:
                    return tuple(paths)
    return tuple(paths)


def _search_candidate_files(
    *,
    project_root: Path,
    candidate_paths: tuple[str, ...],
    query_terms: set[str],
    query_variants: tuple[str, ...],
    skipped_files: int,
) -> tuple[list[dict[str, object]], int, int, int, bool]:
    matches: list[dict[str, object]] = []
    scanned_files = 0
    read_files = 0
    bytes_read = 0
    early_stop = False
    for relative_path in sorted(candidate_paths, key=lambda path: (_search_path_rank(path), path)):
        if scanned_files >= SEARCH_CODE_MAX_FILES:
            early_stop = True
            break
        target = (project_root / relative_path).resolve()
        if not target.is_relative_to(project_root):
            skipped_files += 1
            continue
        try:
            if not target.is_file():
                skipped_files += 1
                continue
            size = target.stat().st_size
            if size > SEARCH_CODE_MAX_BYTES:
                skipped_files += 1
                continue
            if bytes_read + size > SEARCH_CODE_MAX_TOTAL_BYTES:
                early_stop = True
                break
        except OSError:
            skipped_files += 1
            continue
        scanned_files += 1
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            skipped_files += 1
            continue
        read_files += 1
        bytes_read += size
        for line_number, line in enumerate(lines, start=1):
            if any(variant in line for variant in query_variants):
                context = _candidate_context(lines, line_number, relative_path)
                matches.append(
                    {
                        "path": relative_path,
                        "line": line_number,
                        "excerpt": line.strip()[:240],
                        "symbol": context["symbol"],
                        "structural_context": context,
                        "semantic_context": context["semantic_context"],
                        "score": _candidate_score(relative_path, line, context, query_terms),
                    }
                )
                break
        if len(matches) >= SEARCH_CODE_MAX_MATCHES:
            early_stop = True
            break
    matches.sort(
        key=lambda item: (
            -int(item["score"]),
            _search_path_rank(str(item["path"])),
            str(item["path"]),
        )
    )
    return matches, scanned_files, read_files, bytes_read, early_stop


def _search_path_excluded(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    return any(part in SEARCH_CODE_EXCLUDED_DIRS for part in parts)


def _search_code_index(
    session: Session,
    task: ChangeTask,
    query: str,
    *,
    revision: str,
) -> list[dict[str, object]]:
    terms = _semantic_terms(query)
    if not terms:
        return []
    ready_index_id = session.scalar(
        select(CodeIndex.id)
        .where(CodeIndex.project_id == task.project_id)
        .where(CodeIndex.revision == revision)
        .where(CodeIndex.status == CodeIndexStatus.READY)
        .limit(1)
    )
    if ready_index_id is None:
        return []
    rows = session.scalars(
        select(CodeSymbol)
        .where(CodeSymbol.project_id == task.project_id)
        .where(CodeSymbol.revision == revision)
        .order_by(CodeSymbol.relative_path, CodeSymbol.qualified_name)
    ).all()
    matches: list[dict[str, object]] = []
    dirty_paths = _changed_paths(session, task.id, transaction_id=None)
    for symbol in rows:
        if symbol.relative_path in dirty_paths:
            continue
        haystack = f"{symbol.relative_path} {symbol.qualified_name}".lower()
        if not any(term.lower() in haystack for term in terms):
            continue
        matches.append(
            {
                "path": symbol.relative_path,
                "line": 1,
                "excerpt": symbol.qualified_name,
                "symbol": symbol.qualified_name,
                "structural_context": {
                    "symbol": symbol.qualified_name,
                    "semantic_context": _index_semantic_context(symbol.relative_path),
                },
                "semantic_context": _index_semantic_context(symbol.relative_path),
                "score": _index_candidate_score(symbol.relative_path, symbol.qualified_name, terms),
                "evidence": f"code-index://{revision}/{symbol.id}",
            }
        )
        if len(matches) >= SEARCH_CODE_INDEX_LIMIT:
            break
    matches.sort(
        key=lambda item: (
            -int(item["score"]),
            _search_path_rank(str(item["path"])),
            str(item["path"]),
        )
    )
    return matches


def _index_semantic_context(relative_path: str) -> list[str]:
    return _semantic_context(relative_path, "", "", None, [])


def _index_candidate_score(relative_path: str, qualified_name: str, query_terms: set[str]) -> int:
    haystack = f"{relative_path} {qualified_name}".lower()
    score = 10
    score += sum(12 for term in query_terms if term.lower() in qualified_name.lower())
    score += sum(6 for term in query_terms if term.lower() in relative_path.lower())
    score += sum(2 for term in query_terms if term.lower() in haystack)
    if relative_path.startswith("frontend/src/"):
        score += 10
    if relative_path.startswith(("backend/tests/", "frontend/src/tests/")):
        score -= 20
    return score


def _search_path_rank(path: str) -> int:
    if path == "frontend/src/app/fixtures.ts":
        return -5
    if path == "frontend/src/app/AppShell.tsx":
        return -4
    if path.startswith("frontend/src/app/"):
        return 0
    if path.startswith("frontend/src/pages/"):
        return 1
    if path.startswith("frontend/src/"):
        return 2
    if path.startswith("backend/src/"):
        return 3
    if "/test" in path or path.endswith(".test.tsx") or path.endswith(".test.ts"):
        return 9
    return 5


def _semantic_terms(query: str) -> set[str]:
    terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query.lower()))
    terms.update(re.findall(r"[\u4e00-\u9fff]{2,}", query))
    return terms


def _text_variants(text: str) -> tuple[str, ...]:
    variants = {text}
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    variants.update(chinese_terms)
    for term in chinese_terms:
        variants.add("".join(f"\\u{ord(char):04x}" for char in term))
    return tuple(item for item in variants if item)


def _candidate_context(lines: list[str], line_number: int, relative_path: str) -> dict[str, object]:
    start = max(1, line_number - 8)
    end = min(len(lines), line_number + 8)
    window = lines[start - 1 : end]
    joined = "\n".join(window)
    line = lines[line_number - 1]
    symbol = _nearest_symbol(lines, line_number)
    class_names = re.findall(r'className=["\']([^"\']+)["\']', joined)
    element_match = re.search(r"<([A-Za-z][A-Za-z0-9.]*)\b", line)
    sibling_labels = re.findall(r'label:\s*["\']([^"\']+)["\']', joined)
    sibling_labels.extend(re.findall(r">([^<>{}]{1,24})<", joined))
    semantic_context = _semantic_context(relative_path, line, joined, symbol, class_names)
    return {
        "symbol": symbol,
        "line_window": {"start": start, "end": end, "excerpt": joined[:500]},
        "jsx_element": element_match.group(1) if element_match else None,
        "class_names": class_names[:8],
        "sibling_labels": [item.strip() for item in sibling_labels if item.strip()][:12],
        "semantic_context": semantic_context,
    }


def _nearest_symbol(lines: list[str], line_number: int) -> str | None:
    patterns = (
        r"export\s+function\s+([A-Za-z0-9_]+)",
        r"function\s+([A-Za-z0-9_]+)",
        r"export\s+const\s+([A-Za-z0-9_]+)\s*=",
        r"const\s+([A-Za-z0-9_]+)\s*=",
    )
    for index in range(line_number - 1, max(-1, line_number - 80), -1):
        for pattern in patterns:
            match = re.search(pattern, lines[index])
            if match:
                return match.group(1)
    return None


def _semantic_context(
    relative_path: str,
    line: str,
    joined: str,
    symbol: str | None,
    class_names: list[str],
) -> list[str]:
    haystack = " ".join(
        [relative_path, line, joined, symbol or "", " ".join(class_names)]
    ).lower()
    contexts: list[str] = []
    for label, markers in (
        ("sidebar", ("sidebar", "aside", "side-")),
        ("navigation", ("navitems", "navigation", "navitem", "nav-item", "<nav", 'classname="nav')),
        ("menu-item", ("menu", "nav-item", "label:", "key:")),
        ("page-heading", ("page-title", "<h1", "heading")),
        ("button", ("<button", "button")),
        ("tab", ("tab", "role=\"tab\"")),
    ):
        if any(marker in haystack for marker in markers):
            contexts.append(label)
    return contexts


def _candidate_score(
    relative_path: str,
    line: str,
    context: dict[str, object],
    query_terms: set[str],
) -> int:
    score = 0
    semantic_context = set(str(item) for item in context.get("semantic_context", []))
    if semantic_context & {"sidebar", "navigation", "menu-item"}:
        score += 80
    if "page-heading" in semantic_context:
        score -= 30
    if relative_path.startswith("frontend/src/app/"):
        score += 20
    if relative_path.startswith("frontend/src/pages/"):
        score += 5
    if relative_path.startswith(("docs/", "backend/", "tests/")) or "/test" in relative_path:
        score -= 50
    sibling_labels = [str(item) for item in context.get("sibling_labels", [])]
    if len(set(sibling_labels)) >= 3:
        score += 20
    line_lower = line.lower()
    score += sum(2 for term in query_terms if term.lower() in line_lower)
    return score


def _apply_patch_action(
    session: Session,
    task: ChangeTask,
    write_context: LazyWriteContext,
    authorization: ExecutionAuthorization,
    action,
):
    total_started = perf_counter()
    raw = action.parameters
    grounding_started = perf_counter()
    _assert_grounded_target(session, task.id, str(raw.relative_path), raw.target_evidence)
    LOGGER.info(
        "[perf] tool.apply_patch.grounding task_id=%s project_id=%s duration_ms=%s",
        task.id,
        task.project_id,
        int((perf_counter() - grounding_started) * 1000),
    )
    parse_started = perf_counter()
    replacements = tuple((str(item.old), str(item.new)) for item in raw.replacements)
    relative_path = str(raw.relative_path)
    expected_sha_started = perf_counter()
    expected_sha256 = str(
        raw.expected_sha256 or _file_sha(Path(task.project.root_path), relative_path)
    )
    expected_sha_ms = int((perf_counter() - expected_sha_started) * 1000)
    patch = StructuredPatch(
        relative_path=relative_path,
        expected_sha256=expected_sha256,
        replacements=replacements,
    )
    LOGGER.info(
        (
            "[perf] tool.apply_patch.parse task_id=%s project_id=%s duration_ms=%s "
            "patch_operations=%s patch_chars=%s expected_hash_ms=%s"
        ),
        task.id,
        task.project_id,
        int((perf_counter() - parse_started) * 1000),
        len(replacements),
        sum(len(old) + len(new) for old, new in replacements),
        expected_sha_ms,
    )
    transaction_started = perf_counter()
    transaction = write_context.ensure_prepared()
    LOGGER.info(
        (
            "[perf] tool.apply_patch.transaction_ensure task_id=%s project_id=%s "
            "duration_ms=%s transaction_id=%s"
        ),
        task.id,
        task.project_id,
        int((perf_counter() - transaction_started) * 1000),
        transaction.id,
    )
    apply_started = perf_counter()
    result = AtomicApplyPatchTool(session, project_root=task.project.root_path).apply(
        task_id=task.id,
        action_id=_current_action_id(session, task.id),
        transaction_id=transaction.id,
        grant=authorization,
        patch=patch,
        revision=authorization.revision,
    )
    LOGGER.info(
        "[perf] tool.apply_patch.inner_apply task_id=%s project_id=%s duration_ms=%s",
        task.id,
        task.project_id,
        int((perf_counter() - apply_started) * 1000),
    )
    LOGGER.info(
        (
            "[perf] tool.apply_patch.total task_id=%s project_id=%s duration_ms=%s "
            "patch_operations=%s"
        ),
        task.id,
        task.project_id,
        int((perf_counter() - total_started) * 1000),
        len(replacements),
    )
    return result


def _assert_grounded_target(
    session: Session,
    task_id: str,
    relative_path: str,
    target_evidence: object | None,
) -> None:
    candidates = _target_candidates_from_evidence(session, task_id)
    if not candidates:
        raise TargetGroundingError("TARGET_EVIDENCE_MISSING: run SEARCH_CODE/READ_FILE first")
    selected = [candidate for candidate in candidates if candidate.get("path") == relative_path]
    if not selected:
        raise TargetGroundingError(
            f"TARGET_EVIDENCE_MISSING: no repository evidence supports {relative_path}"
        )
    selected_score = max(int(candidate.get("score", 0)) for candidate in selected)
    strongest = max(candidates, key=lambda candidate: int(candidate.get("score", 0)))
    strongest_score = int(strongest.get("score", 0))
    if strongest.get("path") != relative_path and strongest_score >= selected_score + 40:
        raise TargetGroundingError(
            "TARGET_MISMATCH: stronger semantic candidate "
            f"{strongest.get('path')} score={strongest_score} selected={relative_path} "
            f"score={selected_score}"
        )
    if target_evidence is None and len(candidates) > 1:
        raise TargetGroundingError(
            "TARGET_EVIDENCE_REQUIRED: multiple literal candidates exist; include "
            "target_evidence explaining selected/rejected candidates"
        )


class TargetGroundingError(RuntimeError):
    code = "TARGET_MISMATCH"


def _target_candidates_from_evidence(session: Session, task_id: str) -> list[dict[str, object]]:
    from se_mentor.models.execution import ToolExecution

    candidates: list[dict[str, object]] = []
    tools = session.scalars(
        select(ToolExecution)
        .where(ToolExecution.task_id == task_id)
        .where(ToolExecution.tool_name.in_(["SEARCH_CODE", "READ_FILE"]))
        .order_by(ToolExecution.created_at, ToolExecution.id)
    ).all()
    for tool in tools:
        try:
            evidence = json.loads(tool.evidence_json)
        except json.JSONDecodeError:
            continue
        result = evidence.get("result") if isinstance(evidence, dict) else None
        if not isinstance(result, dict):
            continue
        if isinstance(result.get("matches"), list):
            for item in result["matches"]:
                if isinstance(item, dict) and item.get("path"):
                    candidates.append(dict(item))
        elif result.get("path"):
            candidates.append(_read_result_candidate(result))
    return candidates


def _read_result_candidate(result: dict[str, object]) -> dict[str, object]:
    excerpt = str(result.get("excerpt") or result.get("content") or "")
    path = str(result.get("path"))
    context = _semantic_context(path, excerpt, excerpt, None, [])
    return {
        "path": path,
        "line": result.get("start_line"),
        "excerpt": excerpt[:500],
        "semantic_context": context,
        "score": _candidate_score(path, excerpt, {"semantic_context": context}, set()),
    }


def _policy_allows_write(
    session: Session, grant: ExecutionAuthorization, patch, *, revision: str
) -> tuple[bool, str]:
    try:
        return _policy_allows_path(session, grant, str(patch.relative_path), revision=revision)
    except Exception as exc:
        return False, exc.__class__.__name__


def _policy_allows_path(
    session: Session, grant: ExecutionAuthorization, relative_path: str, *, revision: str
) -> tuple[bool, str]:
    result = PolicyEnforcer(session).dispatch_write(
        policy_id=grant.policy_id,
        grant=grant,
        relative_path=relative_path,
        revision=revision,
        orchestrator_allowed=True,
        handler=lambda: None,
    )
    return result.allowed, result.reason


def _current_action_id(session: Session, task_id: str) -> str:
    from se_mentor.models.llm import AgentAction

    action = session.scalars(
        select(AgentAction)
        .where(AgentAction.task_id == task_id)
        .order_by(AgentAction.created_at.desc())
    ).first()
    if action is None:
        raise ValueError("agent action not found")
    return action.id


def _changed_paths(
    session: Session, task_id: str, transaction_id: str | None = None
) -> tuple[str, ...]:
    from se_mentor.models.execution import ToolExecution

    statement = select(FileChange.relative_path).where(FileChange.task_id == task_id)
    if transaction_id is not None:
        statement = statement.join(
            ToolExecution, ToolExecution.id == FileChange.tool_execution_id
        ).where(ToolExecution.transaction_id == transaction_id)
    return tuple(row[0] for row in session.execute(statement.order_by(FileChange.created_at)))


def _publish_action_events(session: Session, task_id: str, transaction_id: str) -> None:
    from se_mentor.models.execution import ToolExecution
    from se_mentor.models.llm import AgentAction

    tools = session.scalars(
        select(ToolExecution)
        .where(ToolExecution.task_id == task_id)
        .where(ToolExecution.transaction_id == transaction_id)
        .order_by(ToolExecution.created_at, ToolExecution.id)
    ).all()
    action_ids = [tool.action_id for tool in tools]
    if not action_ids:
        return
    actions = session.scalars(
        select(AgentAction)
        .where(AgentAction.task_id == task_id)
        .where(AgentAction.id.in_(action_ids))
        .order_by(AgentAction.created_at, AgentAction.id)
    ).all()
    tool_rows = {row.action_id: row for row in tools}
    for action in actions:
        BUS.publish(
            task_id=task_id,
            event_type="ACTION_STARTED",
            payload={
                "taskId": task_id,
                "actionId": action.id,
                "actionType": action.action_type,
                "state": "RUNNING",
                "message": _action_message(action.action_type),
            },
        )
        tool = tool_rows.get(action.id)
        BUS.publish(
            task_id=task_id,
            event_type="ACTION_COMPLETED",
            payload={
                "taskId": task_id,
                "actionId": action.id,
                "actionType": action.action_type,
                "state": "COMPLETED"
                if tool is not None and tool.status == "SUCCEEDED"
                else "FAILED",
                "message": _action_done_message(
                    action.action_type, tool.status if tool is not None else "UNKNOWN"
                ),
            },
        )


def _publish_file_change_events(session: Session, task_id: str, transaction_id: str) -> None:
    from se_mentor.models.execution import ToolExecution

    for change in session.scalars(
        select(FileChange)
        .join(ToolExecution, ToolExecution.id == FileChange.tool_execution_id)
        .where(FileChange.task_id == task_id)
        .where(ToolExecution.transaction_id == transaction_id)
        .order_by(FileChange.created_at, FileChange.id)
    ).all():
        BUS.publish(
            task_id=task_id,
            event_type="FILE_CHANGED",
            payload={
                "taskId": task_id,
                "changeId": change.id,
                "path": change.relative_path,
                "changeType": change.change_type,
                "state": "COMPLETED",
                "message": f"changed {change.relative_path}",
            },
        )


def _action_message(action_type: str) -> str:
    if action_type == "READ_FILE":
        return "reading repository context"
    if action_type == "SEARCH_CODE":
        return "locating relevant code"
    if action_type in {"APPLY_PATCH", "CREATE_FILE", "DELETE_FILE"}:
        return "changing files"
    if action_type == "RUN_COMMAND":
        return "running approved command"
    return "processing action"


def _action_done_message(action_type: str, status: str) -> str:
    suffix = "completed" if status == "SUCCEEDED" else "failed"
    return f"{_action_message(action_type)} {suffix}"


def _file_sha(project_root: Path, relative_path: str) -> str:
    target = (project_root / relative_path).resolve()
    if not target.is_relative_to(project_root) or not target.is_file():
        raise ValueError("target path invalid")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _mark_execution_failed(
    session: Session, task: ChangeTask, transaction_id: str | None, exc: Exception
) -> None:
    transaction = (
        session.get(TaskTransaction, transaction_id) if transaction_id is not None else None
    )
    if transaction is not None:
        transaction.state = TransactionState.CONFLICT
    task.status = TaskStatus.FAILED
    task.failure_code = getattr(exc, "code", "EXECUTION_FAILED")
    task.failure_message = _safe_error(exc)
    session.flush()


def _release_lock(session: Session, lock_id: str) -> None:
    from se_mentor.models.execution import WorkspaceLock

    lock = session.get(WorkspaceLock, lock_id)
    if lock is not None and lock.status == WorkspaceLockStatus.ACTIVE:
        lock.status = WorkspaceLockStatus.RELEASED
        lock.released_at = datetime.now(UTC)


def _safe_error(exc: Exception) -> str:
    return " ".join((str(exc) or type(exc).__name__).split())[:360]


def _active_policy(session: Session, task: ChangeTask) -> ExecutionPolicy | None:
    if task.active_policy_id is not None:
        policy = session.get(ExecutionPolicy, task.active_policy_id)
        if policy is not None and policy.status == ExecutionPolicyStatus.ACTIVE:
            return policy
    return session.scalar(
        select(ExecutionPolicy)
        .where(ExecutionPolicy.task_id == task.id)
        .where(ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE)
    )


def _current_authorization(
    session: Session,
    task: ChangeTask,
    *,
    fallback: ExecutionAuthorization,
) -> ExecutionAuthorization:
    active = _active_policy(session, task)
    if active is None:
        return fallback
    if active.id == fallback.policy_id:
        return fallback
    return ExecutionAuthorization.from_policy(active)


def _latest_iteration_id(session: Session, task_id: str) -> str | None:
    from se_mentor.models.task import TaskIteration

    row = session.scalars(
        select(TaskIteration.id)
        .where(TaskIteration.task_id == task_id)
        .order_by(TaskIteration.created_at.desc(), TaskIteration.id.desc())
    ).first()
    return str(row) if row is not None else None


def _json_tuple(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data)
