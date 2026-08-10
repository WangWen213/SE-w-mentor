from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from se_mentor.security.redaction import redact_text


class SideEffectState(StrEnum):
    NONE = "NONE"
    PARTIAL_CHANGES = "PARTIAL_CHANGES"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class ActionableError:
    code: str
    message: str
    side_effect_state: SideEffectState
    task_id: str
    correlation_id: str
    next_steps: tuple[str, ...]


class ErrorMapper:
    def map(
        self,
        *,
        code: str,
        message: str,
        side_effect_state: SideEffectState,
        task_id: str,
        correlation_id: str,
    ) -> ActionableError:
        return ActionableError(
            code=code,
            message=redact_text(message),
            side_effect_state=side_effect_state,
            task_id=task_id,
            correlation_id=correlation_id,
            next_steps=_next_steps(side_effect_state),
        )


def _next_steps(side_effect_state: SideEffectState) -> tuple[str, ...]:
    if side_effect_state == SideEffectState.NONE:
        return ("inspect evidence", "retry")
    if side_effect_state == SideEffectState.PARTIAL_CHANGES:
        return ("inspect evidence", "retain changes", "rollback")
    if side_effect_state == SideEffectState.ROLLED_BACK:
        return ("inspect evidence", "retry from clean state")
    return ("inspect evidence", "verify committed state")
