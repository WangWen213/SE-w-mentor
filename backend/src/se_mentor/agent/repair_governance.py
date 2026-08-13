from __future__ import annotations

from dataclasses import dataclass

from se_mentor.governance.action_classifier import ActionRisk
from se_mentor.validation.evasion import EvasionInput, ValidationEvasionDetector


@dataclass(frozen=True)
class RepairPatch:
    changed_paths: tuple[str, ...]
    commands: tuple[str, ...]
    patch_text: str
    knowledge_revision: str


@dataclass(frozen=True)
class RepairGovernanceDecision:
    allowed: bool
    pause_before_write: bool
    regovernance_required: bool
    invalidates_policy: bool
    reason: str


class RepairGovernance:
    def __init__(
        self,
        *,
        approved_write_paths: tuple[str, ...],
        approved_commands: tuple[str, ...],
        policy_revision: str,
    ) -> None:
        self.approved_write_paths = frozenset(_normalize(path) for path in approved_write_paths)
        self.approved_commands = frozenset(command.lower() for command in approved_commands)
        self.policy_revision = policy_revision

    def evaluate(self, patch: RepairPatch) -> RepairGovernanceDecision:
        changed_paths = {_normalize(path) for path in patch.changed_paths}
        if not changed_paths <= self.approved_write_paths:
            return _pause("repair_scope_expanded")

        commands = {command.lower() for command in patch.commands}
        if not commands <= self.approved_commands:
            return _pause("repair_command_expanded")

        if patch.knowledge_revision != self.policy_revision:
            return _pause("repair_knowledge_stale")

        evasion = ValidationEvasionDetector().detect(
            EvasionInput(
                baseline_test_count=0,
                current_test_count=0,
                diff_text=patch.patch_text,
                command="\n".join(patch.commands),
                baseline_checks=(),
                current_checks=(),
            )
        )
        if evasion.risk is ActionRisk.DENY_HARD:
            return _pause("repair_validation_evasion")

        return RepairGovernanceDecision(
            allowed=True,
            pause_before_write=False,
            regovernance_required=False,
            invalidates_policy=False,
            reason="approved_repair_scope",
        )


def _pause(reason: str) -> RepairGovernanceDecision:
    return RepairGovernanceDecision(
        allowed=False,
        pause_before_write=True,
        regovernance_required=True,
        invalidates_policy=True,
        reason=reason,
    )


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()
