from __future__ import annotations

from collections.abc import Mapping

DEFAULT_CHILD_ENV_ALLOWLIST = frozenset({"PATH", "SystemRoot", "TMP", "TEMP"})


def build_child_env(
    parent_env: Mapping[str, str],
    *,
    allowlist: frozenset[str] = DEFAULT_CHILD_ENV_ALLOWLIST,
) -> dict[str, str]:
    return {key: value for key, value in parent_env.items() if key in allowlist}
