from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletionSnapshot:
    llm_requested_complete: bool
    validators_available: bool
    validation_passed: bool
    pending_approval: bool
    transaction_open: bool
    lock_held: bool
    diff_present: bool
    audit_recorded: bool
    blocking_risk: bool
    read_only: bool = False


@dataclass(frozen=True)
class CompletionDecision:
    can_complete: bool
    reason: str
    final_summary: str


class CompletionGate:
    def evaluate(self, snapshot: CompletionSnapshot) -> CompletionDecision:
        if not snapshot.llm_requested_complete:
            return _deny("not_requested")
        if snapshot.read_only:
            return _allow("read_only_complete")
        if not snapshot.diff_present:
            return _deny("no_diff")
        if not snapshot.validators_available:
            return _deny("validation_inconclusive")
        if not snapshot.validation_passed:
            return _deny("validation_failed")
        if snapshot.pending_approval:
            return _deny("approval_pending")
        if snapshot.blocking_risk:
            return _deny("risk_blocked")
        if snapshot.transaction_open:
            return _deny("transaction_open")
        if snapshot.lock_held:
            return _deny("lock_held")
        if not snapshot.audit_recorded:
            return _deny("audit_missing")
        return _allow("completed_with_changes")


def _allow(reason: str) -> CompletionDecision:
    return CompletionDecision(True, reason, f"complete: {reason}")


def _deny(reason: str) -> CompletionDecision:
    return CompletionDecision(False, reason, f"incomplete: {reason}")
