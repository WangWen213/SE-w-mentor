from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from sqlalchemy.orm import Session

from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.policy.grants import TemporaryGrant

T = TypeVar("T")


@dataclass(frozen=True)
class EnforcementResult:
    allowed: bool
    reason: str


class PolicyEnforcer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def dispatch_write(
        self,
        *,
        policy_id: str,
        grant: TemporaryGrant,
        relative_path: str,
        revision: str,
        orchestrator_allowed: bool,
        handler: Callable[[], T],
    ) -> EnforcementResult:
        policy = self.session.get(ExecutionPolicy, policy_id)
        if policy is None or policy.status != ExecutionPolicyStatus.ACTIVE or not policy.executable:
            return EnforcementResult(False, "inactive_policy")
        if grant.policy_id != policy.id or grant.task_id != policy.task_id:
            return EnforcementResult(False, "grant_mismatch")
        normalized = relative_path.replace("\\", "/")
        if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
            return EnforcementResult(False, "outside_policy")
        if not grant.allows_write(normalized, revision=revision):
            return EnforcementResult(False, "outside_policy")
        if not orchestrator_allowed:
            return EnforcementResult(False, "orchestrator_denied")
        handler()
        return EnforcementResult(True, "allowed")
