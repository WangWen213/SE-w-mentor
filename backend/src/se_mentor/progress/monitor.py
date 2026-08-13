from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from se_mentor.contracts.enums import EventType
from se_mentor.models.validation import ProgressEvent

_SYNONYMS = {
    "repair": "fix",
    "defect": "bug",
    "issue": "bug",
}
_STOPWORDS = {"a", "an", "the"}


@dataclass(frozen=True)
class ProgressSignal:
    plan: str
    evidence_refs: tuple[str, ...]
    failing_tests: int
    changed_paths: tuple[str, ...] = ()
    approvals: int = 0


@dataclass(frozen=True)
class ProgressDecision:
    progress: bool
    score: int
    reason: str


class ProgressMonitor:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        *,
        task_id: str,
        before: ProgressSignal,
        after: ProgressSignal,
    ) -> ProgressDecision:
        reasons: list[str] = []
        score = 0
        new_evidence = sorted(set(after.evidence_refs) - set(before.evidence_refs))
        if new_evidence:
            score += 2
            reasons.append("new evidence")
        if after.failing_tests < before.failing_tests:
            score += 2
            reasons.append("failing tests reduced")
        new_paths = sorted(set(after.changed_paths) - set(before.changed_paths))
        if new_paths:
            score += 1
            reasons.append("patch scope changed")
        if after.approvals > before.approvals:
            score += 1
            reasons.append("approval improved")
        if not reasons and _normalize_plan(before.plan) == _normalize_plan(after.plan):
            reasons.append("rephrasing only")
        elif not reasons:
            reasons.append("no material evidence")

        decision = ProgressDecision(score > 0, score, ", ".join(reasons))
        self.session.add(
            ProgressEvent(
                task_id=task_id,
                event_type=EventType.TOOL_EXECUTED,
                summary=decision.reason,
                evidence_json=json.dumps(
                    {
                        "progress": decision.progress,
                        "score": decision.score,
                        "new_evidence": new_evidence,
                        "new_paths": new_paths,
                    },
                    sort_keys=True,
                ),
            )
        )
        self.session.flush()
        return decision


def _normalize_plan(plan: str) -> str:
    words = re.findall(r"[a-z0-9]+", plan.lower())
    normalized = [_SYNONYMS.get(word, word) for word in words if word not in _STOPWORDS]
    return " ".join(sorted(normalized))
