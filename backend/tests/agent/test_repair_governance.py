from __future__ import annotations

from se_mentor.agent.repair_governance import RepairGovernance, RepairPatch


def test_T077_repair_touching_new_test_file_pauses_before_write() -> None:
    governance = RepairGovernance(
        approved_write_paths=("backend/src/app/api.py",),
        approved_commands=("pytest",),
        policy_revision="rev-1",
    )

    decision = governance.evaluate(
        RepairPatch(
            changed_paths=("backend/src/app/api.py", "backend/tests/test_api.py"),
            commands=("pytest",),
            patch_text="+def test_new_behavior():\n+    assert True\n",
            knowledge_revision="rev-1",
        )
    )

    assert decision.allowed is False
    assert decision.pause_before_write is True
    assert decision.reason == "repair_scope_expanded"
    assert decision.regovernance_required is True
    assert decision.invalidates_policy is True
