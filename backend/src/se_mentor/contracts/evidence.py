from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from se_mentor.contracts.enums import TrustLevel


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    trust_level: TrustLevel
    summary: str
    uri: str | None = None
    sha256: str | None = None
