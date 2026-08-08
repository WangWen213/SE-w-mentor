from __future__ import annotations

from se_mentor.models.task import TaskStatus

LEGAL_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset(
        {TaskStatus.WAITING_FOR_LOCK, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_FOR_LOCK: frozenset(
        {TaskStatus.INITIALIZING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.INITIALIZING: frozenset({TaskStatus.CONTEXT_BUILDING, TaskStatus.BLOCKED}),
    TaskStatus.CONTEXT_BUILDING: frozenset(
        {TaskStatus.DECIDING, TaskStatus.PAUSED, TaskStatus.BLOCKED}
    ),
    TaskStatus.DECIDING: frozenset(
        {TaskStatus.PROPOSAL_REVIEW, TaskStatus.GOVERNING, TaskStatus.BLOCKED}
    ),
    TaskStatus.PROPOSAL_REVIEW: frozenset(
        {TaskStatus.GOVERNING, TaskStatus.PAUSED, TaskStatus.BLOCKED}
    ),
    TaskStatus.GOVERNING: frozenset(
        {TaskStatus.APPROVAL_REQUIRED, TaskStatus.ACTION_PENDING, TaskStatus.BLOCKED}
    ),
    TaskStatus.APPROVAL_REQUIRED: frozenset(
        {TaskStatus.ACTION_PENDING, TaskStatus.PAUSED, TaskStatus.BLOCKED}
    ),
    TaskStatus.ACTION_PENDING: frozenset(
        {TaskStatus.EXECUTING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.EXECUTING: frozenset(
        {TaskStatus.VALIDATING, TaskStatus.REPAIRING, TaskStatus.BLOCKED, TaskStatus.FAILED}
    ),
    TaskStatus.VALIDATING: frozenset(
        {
            TaskStatus.KNOWLEDGE_UPDATING,
            TaskStatus.REPAIRING,
            TaskStatus.COMPLETED,
            TaskStatus.BLOCKED,
        }
    ),
    TaskStatus.REPAIRING: frozenset(
        {TaskStatus.CONTEXT_BUILDING, TaskStatus.STAGNATION_WARNING, TaskStatus.FAILED}
    ),
    TaskStatus.STAGNATION_WARNING: frozenset(
        {TaskStatus.PAUSED, TaskStatus.REPAIRING, TaskStatus.BLOCKED}
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.CONTEXT_BUILDING, TaskStatus.CANCELLED}),
    TaskStatus.KNOWLEDGE_UPDATING: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED}),
    TaskStatus.ROLLING_BACK: frozenset({TaskStatus.FAILED, TaskStatus.BLOCKED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.BLOCKED: frozenset({TaskStatus.CANCELLED}),
    TaskStatus.CANCELLED: frozenset(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in LEGAL_TRANSITIONS[current]
