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
        handler: Callable[[], object],
    ) -> ToolDispatchResult:
        spec = self.registry.get(tool_name)
        if spec is None:
            self._record(task_id, action_id, tool_name, parameters, ToolExecutionStatus.BLOCKED)
            return ToolDispatchResult(ToolStatus.BLOCKED, "unregistered tool", "UNREGISTERED_TOOL")
        if not enforcer():
            self._record(task_id, action_id, tool_name, parameters, ToolExecutionStatus.BLOCKED)
            return ToolDispatchResult(ToolStatus.BLOCKED, "policy denied", "POLICY_DENIED")
        try:
            value = handler()
        except Exception as exc:
            self._record(task_id, action_id, tool_name, parameters, ToolExecutionStatus.FAILED)
            return ToolDispatchResult(ToolStatus.ERROR, str(exc), "TOOL_EXCEPTION")
        self._record(task_id, action_id, tool_name, parameters, ToolExecutionStatus.SUCCEEDED)
        return ToolDispatchResult(ToolStatus.OK, f"{tool_name} completed", value=value)

    def _record(
        self,
        task_id: str,
        action_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        status: ToolExecutionStatus,
    ) -> None:
        self.session.add(
            ToolExecution(
                task_id=task_id,
                action_id=action_id,
                tool_name=tool_name,
                command_summary=tool_name,
                status=status,
                evidence_json=json.dumps(
                    {"tool_name": tool_name, "parameters": parameters, "status": status},
                    sort_keys=True,
                    default=str,
                ),
            )
        )
        self.session.flush()
