from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from se_mentor.validation.failure_classifier import FailureCategory


@dataclass(frozen=True)
class ValidationAttempt:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class FlakyResult:
    category: FailureCategory
    test_name: str
    evidence: tuple[str, ...]
    retry_code_patch: bool
    knowledge_candidate: bool


class FlakyDetector:
    def __init__(self, *, project_root: str | Path, max_retries: int) -> None:
        self.project_root = Path(project_root).resolve()
        self.max_retries = max_retries

    def classify(
        self,
        *,
        test_name: str,
        revision: str,
        environment_hash: str,
        attempts: tuple[ValidationAttempt, ...],
    ) -> FlakyResult:
        bounded = attempts[: self.max_retries]
        statuses = tuple("PASS" if attempt.exit_code == 0 else "FAIL" for attempt in bounded)
        category = (
            FailureCategory.FLAKY_TEST
            if "PASS" in statuses and "FAIL" in statuses
            else (
                FailureCategory.INCONCLUSIVE
                if all(status == "PASS" for status in statuses)
                else FailureCategory.UNIT_TEST_FAILURE
            )
        )
        return FlakyResult(
            category=category,
            test_name=test_name,
            evidence=statuses,
            retry_code_patch=category != FailureCategory.FLAKY_TEST,
            knowledge_candidate=category == FailureCategory.FLAKY_TEST,
        )
