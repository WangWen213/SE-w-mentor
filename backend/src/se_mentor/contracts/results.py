from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from se_mentor.contracts.enums import ToolStatus
from se_mentor.contracts.evidence import EvidenceRef


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ToolStatus
    summary: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    stdout_ref: EvidenceRef | None = None
    stderr_ref: EvidenceRef | None = None
