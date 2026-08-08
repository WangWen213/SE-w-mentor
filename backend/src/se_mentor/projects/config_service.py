from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.config.loader import ConfigLayer, EffectiveConfig, freeze_task_config, merge_config
from se_mentor.config.profiles import ProfileName, profile_layer
from se_mentor.config.schema import ConfigValue, PolicyValue
from se_mentor.models.project import ProjectConfig


@dataclass(frozen=True)
class AuditedEffectiveConfig:
    effective: EffectiveConfig
    hash: str

    @property
    def values(self) -> dict[str, ConfigValue]:
        return self.effective.values

    @property
    def sources(self) -> dict[str, str]:
        return self.effective.sources

    def explain(self, key: str) -> str:
        return self.effective.explain(key)


@dataclass(frozen=True)
class ConfigGateResult:
    can_start_task: bool
    reason: str
    missing_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigExecutionGate:
    required_keys: tuple[str, ...]

    def evaluate(self, config: AuditedEffectiveConfig) -> ConfigGateResult:
        missing = tuple(key for key in self.required_keys if key not in config.values)
        if missing:
            return ConfigGateResult(False, "MISSING_REQUIRED_CONFIG", missing)
        return ConfigGateResult(True, "OK")


def compute_project_effective_config(
    session: Session,
    project_id: str,
    *,
    profile: str | ProfileName,
    task_values: dict[str, object] | None = None,
) -> AuditedEffectiveConfig:
    layers = [
        ConfigLayer(
            "system",
            {
                "shell_policy": PolicyValue.DENY,
                "network_policy": PolicyValue.DENY,
                "allow_repository_upload": False,
            },
        ),
        profile_layer(ProfileName(profile)),
    ]
    latest = session.scalar(
        select(ProjectConfig)
        .where(ProjectConfig.project_id == project_id)
        .order_by(ProjectConfig.version.desc())
        .limit(1)
    )
    if latest is not None:
        layers.append(ConfigLayer(f"project:{latest.version}", _decode_values(latest.config_json)))
    if task_values:
        layers.append(ConfigLayer("task", _decode_mapping(task_values)))
    effective = merge_config(*layers)
    frozen = freeze_task_config(project_id, effective)
    return AuditedEffectiveConfig(effective=effective, hash=frozen.config_hash)


def _decode_values(payload: str) -> dict[str, ConfigValue]:
    return _decode_mapping(cast(dict[str, object], json.loads(payload)))


def _decode_mapping(values: dict[str, object]) -> dict[str, ConfigValue]:
    decoded: dict[str, ConfigValue] = {}
    for key, value in values.items():
        if key.endswith("_policy"):
            decoded[key] = PolicyValue[str(value)]
        elif isinstance(value, bool | str):
            decoded[key] = value
        else:
            raise ValueError(f"unsupported config value for {key}")
    return decoded
