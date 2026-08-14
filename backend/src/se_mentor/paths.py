from __future__ import annotations

import re

_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class ProjectPathError(ValueError):
    pass


def canonical_project_path(path: str) -> str:
    raw = str(path).strip().replace("\\", "/")
    if not raw:
        raise ProjectPathError("project path is empty")
    if raw.startswith("/") or raw.startswith("//") or _WINDOWS_DRIVE_PREFIX.match(raw):
        raise ProjectPathError("project path must be relative")

    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ProjectPathError("project path cannot traverse outside the workspace")
        parts.append(part)
    if not parts:
        raise ProjectPathError("project path is empty")
    return "/".join(parts)


def canonical_project_paths(paths: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for path in paths:
        item = canonical_project_path(str(path))
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)
