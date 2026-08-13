from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from se_mentor.contracts.enums import ToolStatus
from se_mentor.models.execution import ToolExecution, ToolExecutionStatus
from se_mentor.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolDispatchResult:
    status: ToolStatus
    summary: str
    error_code: str | None = None
    value: object | None = None
    tool_execution_id: str | None = None


class ToolDispatcher:
    def __init__(self, session: Session, registry: ToolRegistry) -> None:
        self.session = session
        self.registry = registry

    def dispatch(
        self,
        *,
        task_id: str,
        action_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        enforcer: Callable[[], bool],
        enforcement_reason: Callable[[], str] | None = None,
        handler: Callable[[], object],
    ) -> ToolDispatchResult:
        spec = self.registry.get(tool_name)
        if spec is None:
            execution = self._record(
                task_id, action_id, tool_name, parameters, ToolExecutionStatus.BLOCKED
            )
            return ToolDispatchResult(
                ToolStatus.BLOCKED,
                "unregistered tool",
                "UNREGISTERED_TOOL",
                tool_execution_id=execution.id,
            )
        if not enforcer():
            reason = enforcement_reason() if enforcement_reason is not None else "policy_denied"
            execution = self._record(
                task_id,
                action_id,
                tool_name,
                parameters,
                ToolExecutionStatus.BLOCKED,
                value={"policy_reason": reason},
            )
            return ToolDispatchResult(
                ToolStatus.BLOCKED,
                f"policy denied: {reason}",
                _policy_error_code(reason),
                tool_execution_id=execution.id,
            )
        try:
            value = handler()
        except Exception as exc:
            execution = self._record(
                task_id, action_id, tool_name, parameters, ToolExecutionStatus.FAILED
            )
            return ToolDispatchResult(
                ToolStatus.ERROR,
                str(exc),
                "TOOL_EXCEPTION",
                tool_execution_id=execution.id,
            )
        execution = self._coerce_tool_execution(value) or self._record(
            task_id,
            action_id,
            tool_name,
            parameters,
            ToolExecutionStatus.SUCCEEDED,
            value=value,
        )
        if execution.status != ToolExecutionStatus.SUCCEEDED:
            return ToolDispatchResult(
                ToolStatus.ERROR,
                _failure_summary(tool_name, execution, value),
                "TOOL_FAILED",
                value=value,
                tool_execution_id=execution.id,
            )
        return ToolDispatchResult(
            ToolStatus.OK,
            f"{tool_name} completed",
            value=value,
            tool_execution_id=execution.id,
        )

    def _record(
        self,
        task_id: str,
        action_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        status: ToolExecutionStatus,
        value: object | None = None,
    ) -> ToolExecution:
        execution = ToolExecution(
            task_id=task_id,
            action_id=action_id,
            tool_name=tool_name,
            command_summary=tool_name,
            status=status,
            evidence_json=json.dumps(
                _evidence_payload(tool_name, parameters, status, value),
                sort_keys=True,
                default=str,
            ),
        )
        self.session.add(execution)
        self.session.flush()
        return execution

    def _coerce_tool_execution(self, value: object) -> ToolExecution | None:
        execution = getattr(value, "tool_execution", None)
        if isinstance(execution, ToolExecution):
            return execution
        execution_id = getattr(value, "tool_execution_id", None)
        if isinstance(execution_id, str):
            return self.session.get(ToolExecution, execution_id)
        return None


def _failure_summary(tool_name: str, execution: ToolExecution, value: object) -> str:
    details: dict[str, object] = {
        "tool_name": tool_name,
        "status": execution.status,
        "exit_code": execution.exit_code,
    }
    stdout = getattr(value, "stdout", None)
    stderr = getattr(value, "stderr", None)
    if isinstance(stdout, str) and stdout:
        details["stdout"] = stdout[:1000]
    if isinstance(stderr, str) and stderr:
        details["stderr"] = stderr[:1000]
    return json.dumps(details, ensure_ascii=False, sort_keys=True)


def _evidence_payload(
    tool_name: str,
    parameters: dict[str, Any],
    status: ToolExecutionStatus,
    value: object | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "tool_name": tool_name,
        "parameters": parameters,
        "status": status,
    }
    if value is not None:
        payload["result"] = _trim_value(value)
    return payload


def _trim_value(value: object) -> object:
    if isinstance(value, str):
        return value[:4000]
    if isinstance(value, dict):
        return {str(key): _trim_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_trim_value(item) for item in value[:20]]
    return value


def _policy_error_code(reason: str) -> str:
    mapping = {
        "inactive_policy": "POLICY_MISSING",
        "grant_mismatch": "POLICY_GRANT_MISMATCH",
        "orchestrator_denied": "POLICY_ORCHESTRATOR_DENIED",
        "outside_policy": "POLICY_DENIED_WRITE_PATH",
    }
    return mapping.get(reason, "POLICY_DENIED")
