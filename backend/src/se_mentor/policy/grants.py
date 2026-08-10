from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.models.approval import ExecutionPolicy, ExecutionPolicyStatus


@dataclass(frozen=True)
class TemporaryGrant:
    task_id: str
    action_id: str
    policy_id: str
    proposal_hash: str
    revision: str
    write_paths: tuple[str, ...]
    commands: tuple[str, ...]
    protected_paths: tuple[str, ...]
    revoked: bool = False

    def allows_write(self, relative_path: str, *, revision: str) -> bool:
        if self.revoked or revision != self.revision:
            return False
        normalized = relative_path.replace("\\", "/")
        return normalized in self.write_paths and normalized not in self.protected_paths


class TemporaryGrantService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        policy_id: str,
        *,
        write_paths: tuple[str, ...],
        commands: tuple[str, ...],
    ) -> TemporaryGrant:
        policy = self.session.get(ExecutionPolicy, policy_id)
        if policy is None:
            raise ValueError("execution policy not found")
        if policy.status != ExecutionPolicyStatus.ACTIVE or not policy.executable:
            raise ValueError("inactive_policy")
        allowed_writes = set(_json_tuple(policy.write_paths_json))
        allowed_commands = set(_json_list(policy.commands_json))
        requested_writes = set(_normalize(write_paths))
        requested_commands = set(commands)
        if not requested_writes.issubset(allowed_writes) or not requested_commands.issubset(
            allowed_commands
        ):
            raise ValueError("expand_scope")
        return TemporaryGrant(
            task_id=policy.task_id,
            action_id=policy.action_id,
            policy_id=policy.id,
            proposal_hash=policy.proposal_hash,
            revision=policy.revision,
            write_paths=tuple(sorted(requested_writes)),
            commands=tuple(sorted(requested_commands)),
            protected_paths=_json_tuple(policy.protected_paths_json),
        )


def _json_tuple(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(str(item).replace("\\", "/") for item in data)


def _json_list(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data)


def _normalize(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path.replace("\\", "/") for path in paths)
