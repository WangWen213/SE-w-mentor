from __future__ import annotations

from se_mentor.governance.action_classifier import ActionRisk
from se_mentor.validation.evasion import EvasionInput, ValidationEvasionDetector


def test_T075_removed_assertions_skips_and_or_true_are_detected_before_completion() -> None:
    detector = ValidationEvasionDetector()

    result = detector.detect(
        EvasionInput(
            baseline_test_count=12,
            current_test_count=8,
            diff_text="-    assert response.status_code == 200\n+    pytest.skip('later')\n",
            command="pytest tests/unit || true",
            baseline_checks=("unit", "lint", "type"),
            current_checks=("unit",),
        )
    )
    normal = detector.detect(
        EvasionInput(
            baseline_test_count=12,
            current_test_count=13,
            diff_text="+    assert response.status_code == 200\n",
            command="pytest",
            baseline_checks=("unit",),
            current_checks=("unit",),
        )
    )

    assert result.risk == ActionRisk.DENY_HARD
    assert "removed assertions" in result.reasons
    assert "suppressed validation failure" in result.reasons
    assert "validation checks removed" in result.reasons
    assert normal.risk == ActionRisk.SAFE
