from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FailureCategory(StrEnum):
    COMPILE_ERROR = "COMPILE_ERROR"
    UNIT_TEST_FAILURE = "UNIT_TEST_FAILURE"
    INTEGRATION_TEST_FAILURE = "INTEGRATION_TEST_FAILURE"
    CONTRACT_FAILURE = "CONTRACT_FAILURE"
    MIGRATION_FAILURE = "MIGRATION_FAILURE"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    FLAKY_TEST = "FLAKY_TEST"
    VALIDATION_EVASION = "VALIDATION_EVASION"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class FailureClassification:
    category: FailureCategory
    confidence: float
    evidence: str


class FailureClassifier:
    def classify(
        self,
        *,
        validation_type: str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> FailureClassification:
        combined = f"{stdout}\n{stderr}"
        if exit_code is None:
            return FailureClassification(
                FailureCategory.INCONCLUSIVE,
                0.3,
                "missing exit code",
            )
        if _environment_error(combined):
            return FailureClassification(
                FailureCategory.ENVIRONMENT_FAILURE,
                0.9,
                _first_line(combined),
            )
        structured = _parse_json(stdout)
        if isinstance(structured, dict):
            failed = int(structured.get("failed", 0) or 0)
            errors = int(structured.get("errors", 0) or 0)
            evidence = _structured_evidence(structured)
            if failed or errors:
                return FailureClassification(
                    _category_for(validation_type),
                    0.85,
                    evidence,
                )
        if exit_code != 0 and combined.strip():
            return FailureClassification(_category_for(validation_type), 0.6, _first_line(combined))
        return FailureClassification(
            FailureCategory.INCONCLUSIVE,
            0.2,
            "unknown validation output",
        )


def _environment_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "modulenotfounderror",
            "command not found",
            "access is denied",
            "no such file or directory",
        )
    )


def _category_for(validation_type: str) -> FailureCategory:
    normalized = validation_type.upper()
    if normalized == "CONTRACT":
        return FailureCategory.CONTRACT_FAILURE
    if normalized == "MIGRATION":
        return FailureCategory.MIGRATION_FAILURE
    if normalized == "INTEGRATION":
        return FailureCategory.INTEGRATION_TEST_FAILURE
    return FailureCategory.UNIT_TEST_FAILURE


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _structured_evidence(data: dict[str, Any]) -> str:
    failures = data.get("failures", [])
    if isinstance(failures, list) and failures and isinstance(failures[0], dict):
        return str(failures[0].get("nodeid", "structured failure"))
    return "structured validation failure"


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no output")
