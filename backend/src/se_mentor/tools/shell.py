from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from se_mentor.models.execution import (
    TaskTransaction,
    ToolExecution,
    ToolExecutionStatus,
    TransactionState,
)
from se_mentor.policy.grants import ExecutionAuthorization, TemporaryGrant
from se_mentor.security.process_env import build_child_env

_SHELL_PROGRAMS = {"cmd", "powershell", "pwsh", "bash", "sh"}
_APPROVAL_REQUIRED_PROGRAMS = {"pip", "pip3", "npm", "pnpm", "yarn"}


class ShellToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShellResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    tool_execution_id: str | None = None


class ShellTool:
    def __init__(
        self,
        session: Session,
        *,
        project_root: str | Path,
        parent_env: dict[str, str],
        max_output_chars: int = 4096,
    ) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()
        self.parent_env = parent_env
        self.max_output_chars = max_output_chars

    def run(
        self,
        *,
        task_id: str,
        action_id: str,
        transaction_id: str | None,
        grant: TemporaryGrant | ExecutionAuthorization,
        program: str,
        args: tuple[str, ...],
        cwd: str,
        revision: str,
        timeout_seconds: float = 30,
    ) -> ShellResult:
        transaction = (
            self._prepared_transaction(transaction_id, task_id)
            if transaction_id is not None
            else None
        )
        cwd_path = (self.project_root / cwd).resolve()
        if not cwd_path.is_relative_to(self.project_root):
            raise ShellToolError("cwd escape")
        program_name = Path(program).name.lower()
        if program_name in _SHELL_PROGRAMS or any(arg.lower() in {"-lc", "/c"} for arg in args):
            raise ShellToolError("command injection blocked")
        if program_name in _APPROVAL_REQUIRED_PROGRAMS and "install" in {
            arg.lower() for arg in args
        }:
            raise ShellToolError("approval required command")
        if "RUN_COMMAND" not in grant.commands and program not in grant.commands:
            raise ShellToolError("command not granted")

        try:
            completed = subprocess.run(
                [program, *args],
                cwd=cwd_path,
                env=build_child_env(self.parent_env),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            result = ShellResult(
                None,
                "",
                f"program not found: {program}",
                False,
                False,
            )
            execution = self._record(transaction, task_id, action_id, program, args, result)
            return ShellResult(
                None,
                "",
                f"program not found: {program}",
                False,
                False,
                execution.id,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _to_text(exc.stdout)
            stderr = _to_text(exc.stderr)
            truncated_stdout, truncated_stderr, truncated = _truncate(
                stdout,
                stderr,
                self.max_output_chars,
            )
            result = ShellResult(None, truncated_stdout, truncated_stderr, True, truncated)
            execution = self._record(transaction, task_id, action_id, program, args, result)
            return ShellResult(
                None, truncated_stdout, truncated_stderr, True, truncated, execution.id
            )

        stdout, stderr, truncated = _truncate(
            completed.stdout,
            completed.stderr,
            self.max_output_chars,
        )
        result = ShellResult(completed.returncode, stdout, stderr, False, truncated)
        execution = self._record(transaction, task_id, action_id, program, args, result)
        return ShellResult(completed.returncode, stdout, stderr, False, truncated, execution.id)

    def _prepared_transaction(self, transaction_id: str, task_id: str) -> TaskTransaction:
        transaction = self.session.get(TaskTransaction, transaction_id)
        if (
            transaction is None
            or transaction.task_id != task_id
            or transaction.state != TransactionState.PREPARED
            or transaction.manifest_artifact_ref is None
        ):
            raise ShellToolError("prepared transaction required")
        return transaction

    def _record(
        self,
        transaction: TaskTransaction | None,
        task_id: str,
        action_id: str,
        program: str,
        args: tuple[str, ...],
        result: ShellResult,
    ) -> ToolExecution:
        status = (
            ToolExecutionStatus.CANCELLED
            if result.timed_out
            else (
                ToolExecutionStatus.SUCCEEDED
                if result.exit_code == 0
                else ToolExecutionStatus.FAILED
            )
        )
        execution = ToolExecution(
            task_id=task_id,
            action_id=action_id,
            transaction_id=transaction.id if transaction is not None else None,
            tool_name="RUN_COMMAND",
            command_summary=program,
            status=status,
            exit_code=result.exit_code,
            evidence_json=json.dumps(
                {
                    "program": program,
                    "args": args,
                    "timed_out": result.timed_out,
                    "truncated": result.truncated,
                },
                sort_keys=True,
            ),
        )
        self.session.add(execution)
        self.session.flush()
        return execution


def _truncate(stdout: str, stderr: str, max_chars: int) -> tuple[str, str, bool]:
    combined = len(stdout) + len(stderr)
    if combined <= max_chars:
        return stdout, stderr, False
    stdout_budget = max_chars // 2
    stderr_budget = max_chars - stdout_budget
    return stdout[:stdout_budget], stderr[:stderr_budget], True


def _to_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
