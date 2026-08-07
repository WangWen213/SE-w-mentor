from __future__ import annotations

import json

import pytest

from se_mentor.config.loader import ConfigLayer, ConfigMergeError, freeze_task_config, merge_config
from se_mentor.config.profiles import ProfileName, profile_layer
from se_mentor.config.schema import PolicyValue


def test_T005_task_config_cannot_relax_system_deny_rule() -> None:
    system = ConfigLayer(
        name="system",
        values={
            "shell_policy": PolicyValue.DENY_HARD,
            "network_policy": PolicyValue.DENY,
            "llm_provider": "mock",
            "allow_arbitrary_repo_paths": False,
            "allow_repository_upload": False,
        },
    )
    profile = profile_layer(ProfileName.LOCAL_FULL)
    project = ConfigLayer(
        name="project",
        values={
            "shell_policy": PolicyValue.DENY,
            "network_policy": PolicyValue.DENY_HARD,
            "llm_provider": "configured",
        },
    )
    task = ConfigLayer(
        name="task",
        values={
            "shell_policy": PolicyValue.ALLOW,
            "network_policy": PolicyValue.ALLOW,
            "allow_repository_upload": True,
        },
    )

    effective = merge_config(system, profile, project, task)

    assert effective.values["shell_policy"] is PolicyValue.DENY_HARD
    assert effective.sources["shell_policy"] == "system"
    assert effective.values["network_policy"] is PolicyValue.DENY_HARD
    assert effective.sources["network_policy"] == "project"
    assert "task attempted to relax shell_policy" in effective.explain("shell_policy")
    assert "task attempted to relax network_policy" in effective.explain("network_policy")

    frozen = freeze_task_config("task-1", effective)
    changed_project = ConfigLayer(
        name="project",
        values={"network_policy": PolicyValue.ALLOW, "llm_provider": "configured"},
    )
    changed_effective = merge_config(system, profile, changed_project, task)
    changed_frozen = freeze_task_config("task-2", changed_effective)

    assert frozen.config_hash != changed_frozen.config_hash
    assert frozen.values["network_policy"] is PolicyValue.DENY_HARD
    assert frozen.version == 1
    assert "secret" not in json.dumps(frozen.to_json_safe_dict()).lower()
    assert "api_key" not in json.dumps(frozen.to_json_safe_dict()).lower()

    cloud = merge_config(system, profile_layer(ProfileName.CLOUD_DEMO))
    assert cloud.values["allow_arbitrary_repo_paths"] is False
    assert cloud.values["allow_repository_upload"] is False
    assert cloud.values["llm_provider"] == "mock"
    assert cloud.values["shell_policy"] is PolicyValue.DENY_HARD
    assert cloud.values["network_policy"] is PolicyValue.DENY_HARD

    with pytest.raises(ConfigMergeError, match="unknown config key"):
        merge_config(system, ConfigLayer(name="task", values={"openai_api_key": "sk-secret"}))
