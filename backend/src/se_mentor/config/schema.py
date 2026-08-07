from __future__ import annotations

from enum import Enum


class PolicyValue(Enum):
    ALLOW = 0
    DENY = 1
    DENY_HARD = 2


type ConfigValue = PolicyValue | str | bool

POLICY_KEYS = {"shell_policy", "network_policy"}
BOOLEAN_RESTRICTIVE_KEYS = {"allow_arbitrary_repo_paths", "allow_repository_upload"}
STRING_KEYS = {"llm_provider"}
KNOWN_CONFIG_KEYS = POLICY_KEYS | BOOLEAN_RESTRICTIVE_KEYS | STRING_KEYS


def json_safe_value(value: ConfigValue) -> str | bool:
    if isinstance(value, PolicyValue):
        return value.name
    return value
