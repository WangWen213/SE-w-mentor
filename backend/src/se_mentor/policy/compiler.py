from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.models.approval import (
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionPolicy,
    ExecutionPolicyStatus,
)
from se_mentor.models.governance import GovernanceDecision, GovernanceVerdict
from se_mentor.paths import canonical_project_paths


class ExecutionPolicyCompiler:
    def __init__(self, session: Session) -> None:
        self.session = session

    def compile(
        self,
        *,
        governance_decision_id: str,
        read_paths: tuple[str, ...],
        write_paths: tuple[str, ...],
        commands: tuple[str, ...],
        protected_paths: tuple[str, ...],
        network: dict[str, object],
        resource_limits: dict[str, object],
    ) -> ExecutionPolicy:
        decision = self.session.get(GovernanceDecision, governance_decision_id)
        if decision is None:
            raise ValueError("governance decision not found")
        if decision.action_id is None:
            raise ValueError("execution policy requires an action-bound decision")
        approval = self._approved_request(decision)
        executable = decision.decision == GovernanceVerdict.ALLOW or approval is not None
        read_paths = canonical_project_paths(read_paths)
        write_paths = canonical_project_paths(write_paths)
        protected_paths = canonical_project_paths(protected_paths)
        write_grants = tuple(sorted(write_paths)) if executable else ()
        command_grants = tuple(sorted(commands)) if executable else ()
        if decision.decision == GovernanceVerdict.BLOCK:
            executable = False
            write_grants = ()
            command_grants = ()
        for active in self.session.scalars(
            select(ExecutionPolicy).where(
                ExecutionPolicy.task_id == decision.task_id,
                ExecutionPolicy.status == ExecutionPolicyStatus.ACTIVE,
            )
        ):
            active.status = ExecutionPolicyStatus.SUPERSEDED
        policy = ExecutionPolicy(
            task_id=decision.task_id,
            action_id=decision.action_id,
            governance_decision_id=decision.id,
            approval_request_id=approval.id if approval is not None else None,
            proposal_hash=decision.proposal_hash,
            revision=decision.revision,
            status=ExecutionPolicyStatus.ACTIVE,
            executable=executable,
            read_paths_json=json.dumps(tuple(sorted(read_paths))),
            write_paths_json=json.dumps(write_grants),
            protected_paths_json=json.dumps(tuple(sorted(protected_paths))),
            commands_json=json.dumps(command_grants),
            network_json=json.dumps(network, sort_keys=True),
            resource_limits_json=json.dumps(resource_limits, sort_keys=True),
            invalidation_json=json.dumps(
                {
                    "approval_required": decision.approval_required,
                    "governance_decision_id": decision.id,
                    "proposal_hash": decision.proposal_hash,
                    "revision": decision.revision,
                    "rule_set_version": decision.rule_set_version,
                },
                sort_keys=True,
            ),
            evidence_json=json.dumps(
                {
                    "decision": decision.decision,
                    "approval_request_id": approval.id if approval is not None else None,
                },
                sort_keys=True,
                default=str,
            ),
        )
        self.session.add(policy)
        self.session.flush()
        return policy

    def _approved_request(self, decision: GovernanceDecision) -> ApprovalRequest | None:
        return self.session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.governance_decision_id == decision.id,
                ApprovalRequest.proposal_hash == decision.proposal_hash,
                ApprovalRequest.decision_revision == decision.revision,
                ApprovalRequest.status == ApprovalRequestStatus.APPROVED,
            )
        )
