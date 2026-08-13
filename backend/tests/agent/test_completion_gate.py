from __future__ import annotations

from se_mentor.agent.completion_gate import CompletionGate, CompletionSnapshot


def test_T078_llm_complete_cannot_bypass_failed_validation_or_pending_approval() -> None:
    gate = CompletionGate()

    failed_validation = gate.evaluate(
        CompletionSnapshot(
            llm_requested_complete=True,
            validators_available=True,
            validation_passed=False,
            pending_approval=False,
            transaction_open=False,
            lock_held=False,
            diff_present=True,
            audit_recorded=True,
            blocking_risk=False,
        )
    )
    pending_approval = gate.evaluate(
        CompletionSnapshot(
            llm_requested_complete=True,
            validators_available=True,
            validation_passed=True,
            pending_approval=True,
            transaction_open=False,
            lock_held=False,
            diff_present=True,
            audit_recorded=True,
            blocking_risk=False,
        )
    )

    assert failed_validation.can_complete is False
    assert failed_validation.reason == "validation_failed"
    assert pending_approval.can_complete is False
    assert pending_approval.reason == "approval_pending"
