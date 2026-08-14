from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.orm import Session

from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus
from se_mentor.paths import ProjectPathError, canonical_project_path
from se_mentor.policy.grants import ExecutionAuthorization, TemporaryGrant

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
        grant: TemporaryGrant | ExecutionAuthorization,
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
        try:
            normalized = canonical_project_path(relative_path)
        except ProjectPathError:
            return EnforcementResult(False, "outside_policy")
        if not grant.allows_write(normalized, revision=revision):
            return EnforcementResult(False, "outside_policy")
        if not orchestrator_allowed:
            return EnforcementResult(False, "orchestrator_denied")
        handler()
        return EnforcementResult(True, "allowed")
