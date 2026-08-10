from __future__ import annotations

from dataclasses import dataclass

from se_mentor.governance.action_classifier import ActionRisk


@dataclass(frozen=True)
class EvasionInput:
    baseline_test_count: int
    current_test_count: int
    diff_text: str
    command: str
    baseline_checks: tuple[str, ...]
    current_checks: tuple[str, ...]


@dataclass(frozen=True)
class EvasionResult:
    risk: ActionRisk
    reasons: tuple[str, ...]


class ValidationEvasionDetector:
    def detect(self, data: EvasionInput) -> EvasionResult:
        reasons: list[str] = []
        lowered_diff = data.diff_text.lower()
        lowered_command = data.command.lower()
        if "-    assert" in lowered_diff or "-assert" in lowered_diff:
            reasons.append("removed assertions")
        if "pytest.skip" in lowered_diff or "pytest.mark.skip" in lowered_diff:
            reasons.append("skip introduced")
        if "|| true" in lowered_command:
            reasons.append("suppressed validation failure")
        if data.current_test_count < data.baseline_test_count:
            reasons.append("test count decreased")
        removed_checks = sorted(set(data.baseline_checks) - set(data.current_checks))
        if removed_checks:
            reasons.append("validation checks removed")
        risk = ActionRisk.DENY_HARD if _hard_reasons(reasons) else ActionRisk.SAFE
        return EvasionResult(risk, tuple(reasons) if reasons else ("no evasion",))


def _hard_reasons(reasons: list[str]) -> bool:
    return any(
        reason in reasons
        for reason in (
            "removed assertions",
            "skip introduced",
            "suppressed validation failure",
            "validation checks removed",
        )
    )
