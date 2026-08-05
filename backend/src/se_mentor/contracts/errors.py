from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from se_mentor.contracts.enums import StableErrorCode


class StableError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StableErrorCode
    message: str
    retryable: bool = False
