from __future__ import annotations

from fastapi import APIRouter

from se_mentor.api.envelope import ok

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def audit() -> dict[str, object]:
    return ok({"items": []})
