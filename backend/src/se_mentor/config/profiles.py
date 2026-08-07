from __future__ import annotations

from enum import StrEnum

from se_mentor.config.loader import ConfigLayer
from se_mentor.config.schema import PolicyValue


class ProfileName(StrEnum):
    LOCAL_FULL = "LOCAL_FULL"
    CLOUD_DEMO = "CLOUD_DEMO"


def profile_layer(profile: ProfileName) -> ConfigLayer:
    if profile is ProfileName.LOCAL_FULL:
        return ConfigLayer(
            name="profile:LOCAL_FULL",
            values={
                "shell_policy": PolicyValue.ALLOW,
                "network_policy": PolicyValue.ALLOW,
                "llm_provider": "configured",
                "allow_arbitrary_repo_paths": True,
                "allow_repository_upload": False,
            },
        )
    return ConfigLayer(
        name="profile:CLOUD_DEMO",
        values={
            "shell_policy": PolicyValue.DENY_HARD,
            "network_policy": PolicyValue.DENY_HARD,
            "llm_provider": "mock",
            "allow_arbitrary_repo_paths": False,
            "allow_repository_upload": False,
        },
    )
