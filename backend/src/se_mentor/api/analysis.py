from __future__ import annotations

from fastapi import APIRouter

from se_mentor.api.envelope import ok

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/index")
def index_project() -> dict[str, object]:
    return ok({"status": "INDEXED", "evidenceRef": "evidence://analysis/index"})
