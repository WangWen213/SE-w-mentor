from __future__ import annotations

from pathlib import Path

from se_mentor.validation.failure_classifier import FailureCategory
from se_mentor.validation.flaky import FlakyDetector, ValidationAttempt


def test_T074_same_revision_alternating_result_is_flaky_not_code_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    detector = FlakyDetector(project_root=repo, max_retries=3)

    result = detector.classify(
        test_name="tests/test_api.py::test_contract",
        revision="abc123",
        environment_hash="python-3.12",
        attempts=(
            ValidationAttempt(exit_code=1, stdout='{"failed":1}', stderr=""),
            ValidationAttempt(exit_code=0, stdout='{"failed":0}', stderr=""),
            ValidationAttempt(exit_code=1, stdout='{"failed":1}', stderr=""),
        ),
    )

    assert result.category == FailureCategory.FLAKY_TEST
    assert result.retry_code_patch is False
    assert result.test_name == "tests/test_api.py::test_contract"
    assert result.evidence == ("FAIL", "PASS", "FAIL")
    assert result.knowledge_candidate is True
