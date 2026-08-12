from __future__ import annotations

from typing import Any


def ok(data: dict[str, Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta or {}}


def error(
    code: str,
    message: str,
    *,
    meta: dict[str, Any] | None = None,
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    payload.update(details)
    return {"data": None, "error": payload, "meta": meta or {}}
