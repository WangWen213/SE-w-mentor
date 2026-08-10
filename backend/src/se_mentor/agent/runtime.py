from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.models.task import ChangeTask, TaskStatus


class CancellationRequested(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeRunResult:
    cancelled: bool
    safe_state: str
    next_options: tuple[str, ...]


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
    ) -> None:
        self.session = session
        self.runner = runner
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
    ) -> RuntimeRunResult:
        token = self.cancellation_token(task_id)
        if token.cancelled:
            self._mark_task_cancelled(task_id, "CANCELLED_BEFORE_LLM")
            return RuntimeRunResult(
                True,
                "CANCELLED_BEFORE_LLM",
                ("retain_changes", "rollback"),
            )
        token.raise_if_cancelled()
        if self.runner is None:
            raise ValueError("runner required")
        self.runner.run(
            task_id=task_id,
            proposal_hash=proposal_hash,
            revision=revision,
            goal=goal,
        )
        return RuntimeRunResult(False, "ITERATION_COMPLETE", ())

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
