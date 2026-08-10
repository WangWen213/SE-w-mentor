from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from se_mentor.contracts.enums import ToolStatus
from se_mentor.models.validation import ValidationPlan, ValidationRun, ValidationRunStatus
from se_mentor.policy.enforcer import PolicyEnforcer
from se_mentor.policy.grants import TemporaryGrant
from se_mentor.tools.dispatcher import ToolDispatcher
from se_mentor.tools.registry import ToolRegistry
from se_mentor.tools.run_validation import command_for_check


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@dataclass(frozen=True)
class ValidationExecutionResult:
    passed: bool
    dispatch_status: str
    policy_checked: bool


class ValidationExecutor:
    def __init__(
        self,
        session: Session,
        *,
        registry: ToolRegistry,
        log_root: str | Path,
        runner: Callable[[tuple[str, ...]], CommandResult],
    ) -> None:
        self.session = session
        self.registry = registry
        self.log_root = Path(log_root)
        self.runner = runner
        self.policy_checked = False

    def execute(
        self,
        *,
        task_id: str,
        action_id: str,
        plan_id: str,
        policy_id: str,
        grant: TemporaryGrant,
        revision: str,
    ) -> ValidationExecutionResult:
        plan = self.session.get(ValidationPlan, plan_id)
        if plan is None or plan.task_id != task_id:
            raise ValueError("validation plan not found")
        checks = json.loads(plan.required_checks_json)
        passed = True
        last_status = ToolStatus.OK
        for index, check_name in enumerate(checks, start=1):
            command = command_for_check(str(check_name))
            dispatch = ToolDispatcher(self.session, self.registry).dispatch(
                task_id=task_id,
                action_id=action_id,
                tool_name="RUN_VALIDATION",
                parameters={"check": command.check_name, "program": command.program},
                enforcer=lambda: self._policy_allows(
                    policy_id=policy_id,
                    grant=grant,
                    revision=revision,
                ),
                handler=lambda command=command, index=index: self._run_check(
                    plan.id,
                    index,
                    command.check_name,
                    (command.program, *command.args),
                    required=command.required,
                ),
            )
            last_status = dispatch.status
            passed = passed and dispatch.status == ToolStatus.OK and bool(dispatch.value)
        return ValidationExecutionResult(passed, str(last_status), self.policy_checked)

    def _policy_allows(
        self,
        *,
        policy_id: str,
        grant: TemporaryGrant,
        revision: str,
    ) -> bool:
        self.policy_checked = True
        allowed = PolicyEnforcer(self.session).dispatch_write(
            policy_id=policy_id,
            grant=grant,
            relative_path=".",
            revision=revision,
            orchestrator_allowed=True,
            handler=lambda: None,
        )
        return allowed.allowed

    def _run_check(
        self,
        plan_id: str,
        run_order: int,
        check_name: str,
        command: tuple[str, ...],
        *,
        required: bool,
    ) -> bool:
        result = self.runner(command)
        self.log_root.mkdir(parents=True, exist_ok=True)
        artifact = self.log_root / f"{plan_id}-{run_order}-{check_name}.log"
        artifact.write_text(
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            encoding="utf-8",
        )
        status = ValidationRunStatus.PASSED if result.exit_code == 0 else ValidationRunStatus.FAILED
        self.session.add(
            ValidationRun(
                validation_plan_id=plan_id,
                run_order=run_order,
                validation_type="TEST",
                command_summary=" ".join(command),
                exit_code=result.exit_code,
                status=status,
                required=required,
                required_failure=required and result.exit_code != 0,
                failure_category="NONZERO_EXIT" if result.exit_code != 0 else None,
                log_artifact_ref=str(artifact),
            )
        )
        self.session.flush()
        return result.exit_code == 0 or not required
