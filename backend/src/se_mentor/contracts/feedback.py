from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from se_mentor.contracts.enums import FeedbackKind, FeedbackSeverity
from se_mentor.contracts.evidence import EvidenceRef


class FeedbackSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FeedbackKind
    severity: FeedbackSeverity
    message: str
    evidence: EvidenceRef | None = None
