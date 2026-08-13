from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.models.audit import AlertEvent, AlertSeverity, AlertStatus
from se_mentor.models.task import ChangeTask, TaskStatus


@dataclass(frozen=True)
class ActionObservation:
    action_type: str
    target: str
    progress: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class StagnationDecision:
    stagnated: bool
    provider_allowed: bool
    reason: str
    repeated_count: int


class StagnationMonitor:
    def __init__(
        self,
        session: Session,
        *,
        threshold: int,
        max_iterations: int,
        token_budget: int,
    ) -> None:
        self.session = session
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.token_budget = token_budget
        self._last_key_by_task: dict[str, tuple[str, str]] = {}
        self._repeat_count_by_task: dict[str, int] = {}
        self._iteration_count_by_task: dict[str, int] = {}
        self._token_count_by_task: dict[str, int] = {}

    def record(
        self,
        *,
        task_id: str,
        observation: ActionObservation,
        provider_calls: int,
        spent_tokens: int,
    ) -> StagnationDecision:
        self._iteration_count_by_task[task_id] = (
            self._iteration_count_by_task.get(task_id, 0) + provider_calls
        )
        self._token_count_by_task[task_id] = (
            self._token_count_by_task.get(task_id, 0) + spent_tokens
        )
        key = (observation.action_type, observation.target)
        if observation.progress or observation.evidence_refs:
            repeated = 0
        elif self._last_key_by_task.get(task_id) == key:
            repeated = self._repeat_count_by_task.get(task_id, 1) + 1
        else:
            repeated = 1
        self._last_key_by_task[task_id] = key
        self._repeat_count_by_task[task_id] = repeated

        limit_reached = (
            repeated >= self.threshold
            or self._iteration_count_by_task[task_id] >= self.max_iterations
            or self._token_count_by_task[task_id] >= self.token_budget
        )
        if limit_reached:
            self._mark_stagnated(task_id, repeated)
            return StagnationDecision(
                True, False, "semantic stagnation threshold reached", repeated
            )
        return StagnationDecision(False, True, "progress budget available", repeated)

    def _mark_stagnated(self, task_id: str, repeated: int) -> None:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ValueError("task not found")
        task.status = TaskStatus.STAGNATION_WARNING
        task.stagnation_count = repeated
        self.session.add(
            AlertEvent(
                task_id=task_id,
                system_scope=False,
                severity=AlertSeverity.WARNING,
                status=AlertStatus.OPEN,
                summary="semantic stagnation detected",
                evidence_json=json.dumps({"repeated_count": repeated}, sort_keys=True),
            )
        )
        self.session.flush()
