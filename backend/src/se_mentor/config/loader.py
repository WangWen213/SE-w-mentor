from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from se_mentor.config.schema import (
    BOOLEAN_RESTRICTIVE_KEYS,
    KNOWN_CONFIG_KEYS,
    POLICY_KEYS,
    ConfigValue,
    PolicyValue,
    json_safe_value,
)


class ConfigMergeError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigLayer:
    name: str
    values: Mapping[str, ConfigValue]


@dataclass(frozen=True)
class EffectiveConfig:
    values: dict[str, ConfigValue]
    sources: dict[str, str]
    notes: dict[str, list[str]] = field(default_factory=dict)
    version: int = 1

    def explain(self, key: str) -> str:
        source = self.sources.get(key, "unknown")
        notes = "; ".join(self.notes.get(key, []))
        return f"{key} from {source}" + (f"; {notes}" if notes else "")

    def to_json_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "values": {key: json_safe_value(value) for key, value in sorted(self.values.items())},
            "sources": dict(sorted(self.sources.items())),
            "explanations": {key: self.explain(key) for key in sorted(self.values)},
        }


@dataclass(frozen=True)
class FrozenTaskConfig:
    task_id: str
    version: int
    config_hash: str
    values: dict[str, ConfigValue]
    sources: dict[str, str]

    def to_json_safe_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "version": self.version,
            "config_hash": self.config_hash,
            "values": {key: json_safe_value(value) for key, value in sorted(self.values.items())},
            "sources": dict(sorted(self.sources.items())),
        }


def merge_config(*layers: ConfigLayer) -> EffectiveConfig:
    values: dict[str, ConfigValue] = {}
    sources: dict[str, str] = {}
    notes: dict[str, list[str]] = {}

    for layer in layers:
        for key, incoming in layer.values.items():
            if key not in KNOWN_CONFIG_KEYS:
                raise ConfigMergeError(f"unknown config key: {key}")
            if key in POLICY_KEYS:
                _merge_policy(key, incoming, layer.name, values, sources, notes)
            elif key in BOOLEAN_RESTRICTIVE_KEYS:
                _merge_restrictive_bool(key, incoming, layer.name, values, sources, notes)
            else:
                _merge_llm_provider(key, incoming, layer.name, values, sources, notes)

    return EffectiveConfig(values=values, sources=sources, notes=notes)


def freeze_task_config(task_id: str, effective: EffectiveConfig) -> FrozenTaskConfig:
    payload = effective.to_json_safe_dict()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return FrozenTaskConfig(
        task_id=task_id,
        version=effective.version,
        config_hash=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        values=dict(effective.values),
        sources=dict(effective.sources),
    )


def _merge_policy(
    key: str,
    incoming: ConfigValue,
    layer: str,
    values: dict[str, ConfigValue],
    sources: dict[str, str],
    notes: dict[str, list[str]],
) -> None:
    if not isinstance(incoming, PolicyValue):
        raise ConfigMergeError(f"{key} must be a PolicyValue")
    current = values.get(key)
    if current is None or not isinstance(current, PolicyValue) or incoming.value > current.value:
        values[key] = incoming
        sources[key] = layer
        return
    if incoming.value < current.value:
        notes.setdefault(key, []).append(
            f"{layer} attempted to relax {key} from {current.name} to {incoming.name}; "
            f"kept {sources[key]}"
        )


def _merge_restrictive_bool(
    key: str,
    incoming: ConfigValue,
    layer: str,
    values: dict[str, ConfigValue],
    sources: dict[str, str],
    notes: dict[str, list[str]],
) -> None:
    if not isinstance(incoming, bool):
        raise ConfigMergeError(f"{key} must be a bool")
    current = values.get(key)
    if current is False and incoming is True:
        notes.setdefault(key, []).append(f"{layer} attempted to relax {key}; kept {sources[key]}")
        return
    if current is None or incoming is False:
        values[key] = incoming
        sources[key] = layer


def _merge_llm_provider(
    key: str,
    incoming: ConfigValue,
    layer: str,
    values: dict[str, ConfigValue],
    sources: dict[str, str],
    notes: dict[str, list[str]],
) -> None:
    if not isinstance(incoming, str):
        raise ConfigMergeError(f"{key} must be a string")
    current = values.get(key)
    if current == "mock" and incoming != "mock" and sources.get(key) == "profile:CLOUD_DEMO":
        notes.setdefault(key, []).append(
            f"{layer} attempted to relax {key}; kept profile:CLOUD_DEMO"
        )
        return
    values[key] = incoming
    sources[key] = layer
