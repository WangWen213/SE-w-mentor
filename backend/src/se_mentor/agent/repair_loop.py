from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.models.task import ChangeTask, TaskStatus


@dataclass(frozen=True)
class RepairAttempt:
    diff_hash: str
    failure_signature: str
    passed: bool


@dataclass(frozen=True)
class RepairDecision:
    continue_repair: bool
    completed: bool
    distinct_diffs: int
    reason: str


class RepairLoop:
    def __init__(self, session: Session, *, max_repairs: int) -> None:
        self.session = session
        self.max_repairs = max_repairs
        self._attempts_by_task: dict[str, list[RepairAttempt]] = {}

    def record_attempt(self, *, task_id: str, attempt: RepairAttempt) -> RepairDecision:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")

        attempts = self._attempts_by_task.setdefault(task_id, [])
        previous_diffs = {item.diff_hash for item in attempts}
        previous_failures = {item.failure_signature for item in attempts if item.failure_signature}
        attempts.append(attempt)

        task.repair_count += 1
        distinct_diffs = len({item.diff_hash for item in attempts})

        if attempt.passed:
            task.status = TaskStatus.COMPLETED
            self.session.flush()
            return RepairDecision(False, True, distinct_diffs, "repair passed validation")

        repeated_patch = attempt.diff_hash in previous_diffs
        repeated_failure = (
            bool(attempt.failure_signature) and attempt.failure_signature in previous_failures
        )
        limit_reached = task.repair_count >= self.max_repairs
        if repeated_patch or repeated_failure or limit_reached:
            task.status = TaskStatus.STAGNATION_WARNING
            self.session.flush()
            return RepairDecision(False, False, distinct_diffs, "repair progress exhausted")

        task.status = TaskStatus.REPAIRING
        self.session.flush()
        return RepairDecision(True, False, distinct_diffs, "repair budget available")
