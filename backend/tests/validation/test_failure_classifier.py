from __future__ import annotations

from se_mentor.validation.failure_classifier import FailureCategory, FailureClassifier


def test_T072_distinguishes_code_failure_environment_failure_and_inconclusive() -> None:
    classifier = FailureClassifier()

    unit = classifier.classify(
        validation_type="TEST",
        exit_code=1,
        stdout='{"failed": 1, "errors": 0, "failures": [{"nodeid": "test_app.py::test_x"}]}',
        stderr="",
    )
    environment = classifier.classify(
        validation_type="TEST",
        exit_code=1,
        stdout="",
        stderr="ModuleNotFoundError: No module named 'pytest'",
    )
    inconclusive = classifier.classify(
        validation_type="CONTRACT",
        exit_code=None,
        stdout="not structured",
        stderr="",
    )

    assert unit.category == FailureCategory.UNIT_TEST_FAILURE
    assert unit.confidence >= 0.8
    assert "test_app.py::test_x" in unit.evidence
    assert environment.category == FailureCategory.ENVIRONMENT_FAILURE
    assert environment.confidence >= 0.8
    assert inconclusive.category == FailureCategory.INCONCLUSIVE
    assert inconclusive.confidence < 0.5
