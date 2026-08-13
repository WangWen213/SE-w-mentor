from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.models.execution import FileChange
from se_mentor.models.task import ChangeTask, TaskStatus

LOGGER = logging.getLogger("se_mentor.agent.runtime")


class CancellationRequested(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeRunResult:
    cancelled: bool
    safe_state: str
    next_options: tuple[str, ...]
    terminal_state: str = "UNKNOWN"
    reason: str = ""


@dataclass(frozen=True)
class RuntimePolicy:
    max_iterations: int = 8
    max_parse_failures: int = 4
    max_stalled_iterations: int = 3
    max_read_only_corrections: int = 2


@dataclass(frozen=True)
class RuntimeFeedback:
    source: str
    message: str
    value: object | None = None

    def render(self) -> str:
        if self.value is None:
            return f"{self.source}: {self.message}"
        return f"{self.source}: {self.message}. Value: {_json_value(self.value)}"


StagePublisher = Callable[[str, str, str | None], None]
TransactionIdProvider = str | None | Callable[[], str | None]


class CancellationToken:
    def __init__(self) -> None:
        self.cancelled = False
        self.reason: str | None = None
        self._critical_depth = 0

    def cancel(self, reason: str) -> None:
        self.cancelled = True
        self.reason = reason

    def raise_if_cancelled(self) -> None:
        if self.cancelled and self._critical_depth == 0:
            raise CancellationRequested(self.reason or "cancelled")

    @contextmanager
    def atomic_write_section(self) -> Iterator[None]:
        self._critical_depth += 1
        try:
            yield
        finally:
            self._critical_depth -= 1


class AgentRuntime:
    def __init__(
        self,
        session: Session | None = None,
        *,
        runner: SingleTurnAgentRunner | None = None,
        policy: RuntimePolicy | None = None,
    ) -> None:
        self.session = session
        self.runner = runner
        self.policy = policy or RuntimePolicy()
        self._tokens: dict[str, CancellationToken] = {}
        self._children: list[subprocess.Popen[bytes]] = []

    def cancellation_token(self, task_id: str) -> CancellationToken:
        return self._tokens.setdefault(task_id, CancellationToken())

    def request_cancel(self, *, task_id: str, reason: str) -> None:
        self.cancellation_token(task_id).cancel(reason)

    def run_once(
        self,
        *,
        task_id: str,
        proposal_hash: str,
        revision: str,
        goal: str,
        transaction_id: TransactionIdProvider = None,
    ) -> RuntimeRunResult:
        return self.run_task(
            task_id=task_id,
            proposal_hash=proposal_hash,
            revision=revision,
            goal=goal,
            transaction_id=transaction_id,
        )

    def run_task(
        self,
        *,
        task_id: str,
        proposal_hash: str,
        revision: str,
        goal: str,
        transaction_id: TransactionIdProvider = None,
        publish_stage: StagePublisher | None = None,
    ) -> RuntimeRunResult:
        token = self.cancellation_token(task_id)
        if token.cancelled:
            self._mark_task_cancelled(task_id, "CANCELLED_BEFORE_LLM")
            return RuntimeRunResult(
                True,
                "CANCELLED_BEFORE_LLM",
                ("retain_changes", "rollback"),
                "CANCELLED",
                "cancelled before LLM request",
            )
        token.raise_if_cancelled()
        if self.runner is None:
            raise ExecutionPipelineUnavailable("runner required")
        feedback = RuntimeFeedback("initial", "none")
        parse_failures = 0
        stalled_iterations = 0
        read_only_streak = 0
        read_only_corrections = 0
        repeated_action_fingerprints: dict[str, int] = {}
        evidence_fingerprints: set[str] = set()
        observed_paths: set[str] = set()
        run_started = perf_counter()
        provider_calls = 0
        read_actions = 0
        for iteration_index in range(1, self.policy.max_iterations + 1):
            current_file_changes = self._file_change_count(
                task_id, transaction_id=_transaction_id_value(transaction_id)
            )
            write_tool_count = self._write_tool_count(task_id)
            _publish(publish_stage, "CONTEXT_BUILT", "OK", f"iteration={iteration_index}")
            result = self.runner.run(
                task_id=task_id,
                proposal_hash=proposal_hash,
                revision=revision,
                goal=goal,
                feedback=feedback.render(),
                publish_stage=publish_stage,
            )
            provider_calls += 1
            if result.tool_result is None:
                if (result.feedback or "").startswith("governance decision"):
                    _publish(publish_stage, "TASK_PAUSED", "APPROVAL_REQUIRED", result.feedback)
                    raise GovernancePaused(result.feedback or "governance decision")
                parse_failures += 1
                _publish(publish_stage, "ACTION_PARSED", "INVALID", result.feedback)
                if parse_failures >= self.policy.max_parse_failures:
                    _publish(publish_stage, "TASK_FAILED", "ACTION_PARSE_FAILED", result.feedback)
                    raise AgentActionParseExhausted(
                        f"agent action parsing failed {parse_failures} times; "
                        f"last error: {result.feedback or 'unknown'}"
                    )
                feedback = RuntimeFeedback(
                    "parser",
                    (
                        "Previous agent turn did not produce an executable tool action. "
                        f"Reason: {result.feedback or 'unknown'}. "
                        "Return one valid JSON AgentAction. If more repository context is needed, "
                        "use SEARCH_CODE or READ_FILE; after reading, continue with APPLY_PATCH, "
                        "CREATE_FILE, or DELETE_FILE to perform the confirmed code change."
                    ),
                )
                token.raise_if_cancelled()
                continue
            _publish(publish_stage, "ACTION_PARSED", "OK", f"action_id={result.action_id}")
            _publish(publish_stage, "ACTION_GOVERNED", "ALLOW", f"action_id={result.action_id}")
            _publish(
                publish_stage,
                "TOOL_COMPLETED",
                "FAILED" if result.tool_result.error_code else "OK",
                result.tool_result.summary,
            )
            if result.tool_result.error_code is not None:
                if _is_patch_mismatch(result.tool_result.summary):
                    feedback = RuntimeFeedback(
                        "patch",
                        "PATCH_EXACT_TEXT_REQUIRED",
                        {
                            "message": result.tool_result.summary,
                            "instruction": (
                                "The previous patch did not match the current file bytes. "
                                "Use READ_FILE on the selected path or copy the exact source "
                                "excerpt from SEARCH_CODE. The replacement old text must match "
                                "the file exactly, including quotes, indentation, and unicode "
                                "escape sequences such as \\u4efb\\u52a1."
                            ),
                        },
                    )
                    _publish(
                        publish_stage,
                        "FEEDBACK_CREATED",
                        "PATCH_EXACT_TEXT_REQUIRED",
                        result.tool_result.summary,
                    )
                    token.raise_if_cancelled()
                    continue
                if _is_target_grounding_error(result.tool_result.summary):
                    feedback = RuntimeFeedback(
                        "target-grounding",
                        "TARGET_GROUNDING_REQUIRED",
                        {
                            "message": result.tool_result.summary,
                            "instruction": (
                                "Do not write yet. Inspect enough SEARCH_CODE/READ_FILE "
                                "candidates to prove the selected target matches the user's "
                                "semantic UI location. If multiple literal matches exist, "
                                "include target_evidence in APPLY_PATCH explaining selected "
                                "and rejected candidates."
                            ),
                        },
                    )
                    _publish(
                        publish_stage,
                        "FEEDBACK_CREATED",
                        "TARGET_GROUNDING_REQUIRED",
                        result.tool_result.summary,
                    )
                    token.raise_if_cancelled()
                    continue
                _publish(
                    publish_stage,
                    "TASK_FAILED",
                    result.tool_result.error_code,
                    result.tool_result.summary,
                )
                raise ToolExecutionFailed(
                    result.tool_result.summary or result.tool_result.error_code
                )
            if self._has_file_changes(
                task_id, transaction_id=_transaction_id_value(transaction_id)
            ):
                LOGGER.info(
                    (
                        "[perf] time-to-first-write task_id=%s provider_calls=%s "
                        "read_actions=%s elapsed_ms=%s"
                    ),
                    task_id,
                    provider_calls,
                    read_actions,
                    int((perf_counter() - run_started) * 1000),
                )
                _publish(
                    publish_stage,
                    "FILE_CHANGED",
                    "OK",
                    f"tool_execution_id={result.tool_result.tool_execution_id}",
                )
                return RuntimeRunResult(
                    False,
                    "FILES_CHANGED",
                    (),
                    "COMPLETED",
                    "real file change produced",
                )
            action_snapshot = self._latest_action_snapshot(task_id)
            summarized_tool_result = _summarize_tool_result(result.tool_result.value)
            _collect_observed_paths(action_snapshot, summarized_tool_result, observed_paths)
            evidence_fingerprint = _json_value(summarized_tool_result)
            new_evidence = (
                bool(evidence_fingerprint)
                and evidence_fingerprint not in evidence_fingerprints
            )
            evidence_fingerprints.add(evidence_fingerprint)
            action_type = str(action_snapshot.get("action_type") or "")
            if _is_read_only_action(action_type):
                read_actions += 1
            fingerprint = _fingerprint(action_snapshot)
            repeated_action_fingerprints[fingerprint] = (
                repeated_action_fingerprints.get(fingerprint, 0) + 1
            )
            next_file_changes = self._file_change_count(
                task_id, transaction_id=_transaction_id_value(transaction_id)
            )
            next_write_tool_count = self._write_tool_count(task_id)
            material_progress = (
                next_file_changes > current_file_changes
                or next_write_tool_count > write_tool_count
                or _is_write_action(action_type)
                or new_evidence
            )
            if _is_read_only_action(action_type) and not material_progress:
                read_only_streak += 1
            else:
                read_only_streak = 0
            if material_progress:
                stalled_iterations = 0
            else:
                stalled_iterations += 1
            no_material_progress = (
                read_only_streak >= 2 or repeated_action_fingerprints[fingerprint] >= 2
            )
            if (
                next_file_changes == 0
                and next_write_tool_count == 0
                and no_material_progress
                and read_only_corrections < self.policy.max_read_only_corrections
            ):
                read_only_corrections += 1
                feedback = RuntimeFeedback(
                    "corrective",
                    "WRITE_REQUIRED_NO_CHANGE",
                    {
                        "code": "WRITE_REQUIRED_NO_CHANGE",
                        "message": (
                            "The requested task requires a real code modification. "
                            "Repository evidence has been gathered but no WRITE action "
                            "has produced a FileChange. Do not repeat an equivalent "
                            "read/search/run action unless new evidence is strictly necessary. "
                            "If policy permits the intended modification, produce the "
                            "appropriate canonical WRITE AgentAction."
                        ),
                        "read_only_streak": read_only_streak,
                        "repeated_action_fingerprint": fingerprint,
                        "observed_paths": sorted(observed_paths),
                        "last_action": action_snapshot,
                        "last_tool_result": summarized_tool_result,
                        "changed_files": [],
                        "write_tool_executions": next_write_tool_count,
                        "file_change_count": next_file_changes,
                    },
                )
                _publish(
                    publish_stage,
                    "FEEDBACK_CREATED",
                    "WRITE_REQUIRED_NO_CHANGE",
                    f"correction={read_only_corrections}",
                )
                token.raise_if_cancelled()
                continue
            if stalled_iterations >= self.policy.max_stalled_iterations:
                code = (
                    "STALLED_READ_ONLY_LOOP"
                    if next_file_changes == 0
                    and next_write_tool_count == 0
                    and read_only_corrections >= self.policy.max_read_only_corrections
                    else "STALLED"
                )
                _publish(
                    publish_stage, "TASK_FAILED", code, "tools completed without file changes"
                )
                if code == "STALLED_READ_ONLY_LOOP":
                    raise AgentStalledReadOnlyLoop(
                        "agent stalled in read-only loop without producing required file changes"
                    )
                raise AgentStalled(
                    "agent stalled: tools completed without producing required file changes"
                )
            feedback = RuntimeFeedback(
                "Previous tool result",
                result.tool_result.summary,
                {
                    "previous_action": action_snapshot,
                    "tool_result": summarized_tool_result,
                    "changed_files": self._changed_files(
                        task_id, transaction_id=_transaction_id_value(transaction_id)
                    ),
                    "write_tool_executions": next_write_tool_count,
                    "file_change_count": next_file_changes,
                    "read_only_streak": read_only_streak,
                },
            )
            _publish(
                publish_stage,
                "FEEDBACK_CREATED",
                "OK",
                f"iteration={iteration_index}",
            )
            token.raise_if_cancelled()
        _publish(publish_stage, "TASK_FAILED", "MAX_ITERATIONS", str(self.policy.max_iterations))
        raise AgentMaxIterationsExceeded(
            f"agent reached max iterations ({self.policy.max_iterations}) without real file changes"
        )

    def _has_file_changes(self, task_id: str, *, transaction_id: str | None) -> bool:
        return self._file_change_count(task_id, transaction_id=transaction_id) > 0

    def _file_change_count(self, task_id: str, *, transaction_id: str | None) -> int:
        if self.session is None:
            return 0
        statement = select(FileChange.id).where(FileChange.task_id == task_id)
        if transaction_id is not None:
            from se_mentor.models.execution import ToolExecution

            statement = (
                select(FileChange.id)
                .join(ToolExecution, ToolExecution.id == FileChange.tool_execution_id)
                .where(FileChange.task_id == task_id)
                .where(ToolExecution.transaction_id == transaction_id)
            )
        return len(tuple(self.session.scalars(statement)))

    def _changed_files(self, task_id: str, *, transaction_id: str | None) -> list[str]:
        if self.session is None:
            return []
        statement = select(FileChange.relative_path).where(FileChange.task_id == task_id)
        if transaction_id is not None:
            from se_mentor.models.execution import ToolExecution

            statement = (
                select(FileChange.relative_path)
                .join(ToolExecution, ToolExecution.id == FileChange.tool_execution_id)
                .where(FileChange.task_id == task_id)
                .where(ToolExecution.transaction_id == transaction_id)
            )
        return [str(item) for item in self.session.scalars(statement)]

    def _write_tool_count(self, task_id: str) -> int:
        if self.session is None:
            return 0
        from se_mentor.models.execution import ToolExecution

        return len(
            tuple(
                self.session.scalars(
                    select(ToolExecution.id)
                    .where(ToolExecution.task_id == task_id)
                    .where(
                        ToolExecution.tool_name.in_(
                            ["APPLY_PATCH", "CREATE_FILE", "DELETE_FILE"]
                        )
                    )
                )
            )
        )

    def _latest_action_snapshot(self, task_id: str) -> dict[str, object]:
        if self.session is None:
            return {}
        from se_mentor.models.llm import AgentAction

        action = self.session.scalars(
            select(AgentAction)
            .where(AgentAction.task_id == task_id)
            .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
        ).first()
        if action is None:
            return {}
        try:
            parameters = json.loads(action.parameters_summary)
        except json.JSONDecodeError:
            parameters = action.parameters_summary
        return {
            "id": action.id,
            "action_type": action.action_type,
            "parameters": parameters,
            "reason": _extract_reason(parameters),
            "status": action.status,
        }

    def start_process(
        self,
        argv: Sequence[str],
        *,
        cwd: str | Path,
    ) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            list(argv),
            cwd=Path(cwd),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._children.append(process)
        return process

    def terminate_children(self, *, timeout_seconds: float) -> int:
        terminated = 0
        for process in list(self._children):
            if process.poll() is not None:
                self._children.remove(process)
                continue
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_seconds)
            terminated += 1
            self._children.remove(process)
        return terminated

    def _mark_task_cancelled(self, task_id: str, safe_state: str) -> None:
        if self.session is None:
            return
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        task.status = TaskStatus.CANCELLED
        task.failure_code = safe_state
        task.failure_message = "user cancellation requested"
        self.session.flush()


class ExecutionPipelineUnavailable(RuntimeError):
    code = "EXECUTION_PIPELINE_UNAVAILABLE"


class AgentActionParseExhausted(RuntimeError):
    code = "ACTION_PARSE_FAILED"


class AgentMaxIterationsExceeded(RuntimeError):
    code = "MAX_ITERATIONS"


class AgentStalled(RuntimeError):
    code = "STALLED"


class AgentStalledReadOnlyLoop(RuntimeError):
    code = "STALLED_READ_ONLY_LOOP"


class ToolExecutionFailed(RuntimeError):
    code = "TOOL_EXECUTION_FAILED"


class GovernancePaused(RuntimeError):
    code = "GOVERNANCE_PAUSED"


def _publish(
    publisher: StagePublisher | None, stage: str, status: str, detail: str | None = None
) -> None:
    if publisher is not None:
        publisher(stage, status, detail)


def _transaction_id_value(provider: TransactionIdProvider) -> str | None:
    if callable(provider):
        return provider()
    return provider


def _json_value(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _extract_reason(parameters: object) -> str | None:
    if isinstance(parameters, dict):
        value = parameters.get("reason")
        return str(value) if value is not None else None
    return None


def _fingerprint(action_snapshot: dict[str, object]) -> str:
    payload = {
        "action_type": action_snapshot.get("action_type"),
        "parameters": action_snapshot.get("parameters"),
    }
    return _json_value(payload)


def _is_write_action(action_type: str) -> bool:
    return action_type in {"APPLY_PATCH", "CREATE_FILE", "DELETE_FILE"}


def _is_read_only_action(action_type: str) -> bool:
    return action_type in {"READ_FILE", "SEARCH_CODE", "RUN_COMMAND"}


def _collect_observed_paths(
    action_snapshot: dict[str, object], value: object | None, observed_paths: set[str]
) -> None:
    _collect_paths_from_value(action_snapshot.get("parameters"), observed_paths)
    _collect_paths_from_value(value, observed_paths)


def _collect_paths_from_value(value: object, observed_paths: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "relative_path"} and isinstance(item, str):
                observed_paths.add(item)
            else:
                _collect_paths_from_value(item, observed_paths)
        return
    if isinstance(value, list):
        for item in value:
            _collect_paths_from_value(item, observed_paths)


def _summarize_tool_result(value: object | None) -> object | None:
    if isinstance(value, dict):
        if "matches" in value and isinstance(value["matches"], list):
            return {
                "query": value.get("query"),
                "matches": value["matches"][:12],
                "match_count": len(value["matches"]),
            }
        if "content" in value or "excerpt" in value:
            excerpt = str(value.get("excerpt") or value.get("content") or "")
            return {
                "path": value.get("path"),
                "start_line": value.get("start_line"),
                "end_line": value.get("end_line"),
                "excerpt": excerpt[:2500],
                "sha256": value.get("sha256"),
                "truncated": value.get("truncated"),
            }
        return {str(key): _summarize_tool_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_summarize_tool_result(item) for item in value[:12]]
    if isinstance(value, str):
        return value[:2500]
    return value


def _is_target_grounding_error(summary: str) -> bool:
    return any(
        code in summary
        for code in (
            "TARGET_MISMATCH",
            "TARGET_EVIDENCE_MISSING",
            "TARGET_EVIDENCE_REQUIRED",
        )
    )


def _is_patch_mismatch(summary: str) -> bool:
    return "patch mismatch" in summary.lower()
