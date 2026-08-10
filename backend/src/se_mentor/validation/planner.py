from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from se_mentor.models.validation import ValidationPlan, ValidationPlanStatus


@dataclass(frozen=True)
class ImpactValidationInput:
    changed_paths: tuple[str, ...]
    toolchain_frameworks: tuple[str, ...]


class ValidationPlanner:
    def __init__(self, session: Session) -> None:
        self.session = session

    def plan(
        self,
        *,
        task_id: str,
        proposal_id: str,
        execution_policy_id: str,
        revision: str,
        impact: ImpactValidationInput,
    ) -> ValidationPlan:
        checks, inconclusive = _checks_for(impact)
        version = (
            self.session.scalar(
                select(func.max(ValidationPlan.version)).where(
                    ValidationPlan.proposal_id == proposal_id,
                    ValidationPlan.execution_policy_id == execution_policy_id,
                )
            )
            or 0
        ) + 1
        plan = ValidationPlan(
            task_id=task_id,
            proposal_id=proposal_id,
            execution_policy_id=execution_policy_id,
            version=version,
            status=ValidationPlanStatus.ACTIVE,
            required_checks_json=json.dumps(checks),
            evidence_json=json.dumps(
                {
                    "revision": revision,
                    "changed_paths": impact.changed_paths,
                    "toolchain_frameworks": impact.toolchain_frameworks,
                    "inconclusive_preconditions": inconclusive,
                },
                sort_keys=True,
            ),
        )
        self.session.add(plan)
        self.session.flush()
        return plan


def _checks_for(impact: ImpactValidationInput) -> tuple[list[str], list[str]]:
    checks: set[str] = set()
    inconclusive: list[str] = []
    if "pytest" in impact.toolchain_frameworks:
        checks.add("unit")
    else:
        inconclusive.append("python test framework unavailable")
    for path in impact.changed_paths:
        lowered = path.lower()
        if "/api/" in lowered or lowered.endswith("api.py"):
            checks.add("contract")
        if "migration" in lowered or "schema" in lowered:
            checks.add("migration-empty-db")
            checks.add("migration-existing-db")
        if "test" in lowered or "validation" in lowered:
            checks.add("validation-integrity")
    return sorted(checks), inconclusive
