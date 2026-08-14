from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RuntimeProfile(StrEnum):
    LOCAL_FULL = "LOCAL_FULL"
    CLOUD_DEMO = "CLOUD_DEMO"
    ONLINE_SAFE = "ONLINE_SAFE"


class RuntimeProfileError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeSettings:
    profile: RuntimeProfile
    runtime_root: Path
    demo_workspace_root: Path
    trust_proxy: bool = False

    @property
    def cloud_demo(self) -> bool:
        return self.profile is RuntimeProfile.CLOUD_DEMO

    @property
    def online_safe(self) -> bool:
        return self.profile is RuntimeProfile.ONLINE_SAFE


_PROFILE_ENV = "SE_MENTOR_RUNTIME_PROFILE"
_LOCAL_RUNTIME_ROOT_ENV = "SE_MENTOR_RUNTIME_ROOT"
_DEMO_WORKSPACE_ENV = "SE_MENTOR_DEMO_WORKSPACE"
_DEMO_RUNTIME_ROOT_ENV = "SE_MENTOR_DEMO_RUNTIME_ROOT"
_TRUST_PROXY_ENV = "SE_MENTOR_TRUST_PROXY"


def get_runtime_profile(env: dict[str, str] | None = None) -> RuntimeProfile:
    source = os.environ if env is None else env
    raw = source.get(_PROFILE_ENV)
    if raw is None or not raw.strip():
        return RuntimeProfile.LOCAL_FULL
    normalized = raw.strip().upper()
    try:
        return RuntimeProfile(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RuntimeProfile)
        raise RuntimeProfileError(f"{_PROFILE_ENV} must be one of: {allowed}") from exc


def get_runtime_settings(env: dict[str, str] | None = None) -> RuntimeSettings:
    source = os.environ if env is None else env
    profile = get_runtime_profile(source)
    return RuntimeSettings(
        profile=profile,
        runtime_root=_runtime_root(profile, source),
        demo_workspace_root=_demo_workspace_root(source),
        trust_proxy=_truthy(source.get(_TRUST_PROXY_ENV)),
    )


def _runtime_root(profile: RuntimeProfile, env: dict[str, str]) -> Path:
    if profile is RuntimeProfile.CLOUD_DEMO:
        configured = env.get(_DEMO_RUNTIME_ROOT_ENV)
        return (
            Path(configured).expanduser().resolve()
            if configured
            else (_repo_root() / ".tmp" / "cloud-demo-runtime").resolve()
        )
    if profile is RuntimeProfile.ONLINE_SAFE:
        configured = env.get(_LOCAL_RUNTIME_ROOT_ENV)
        return (
            Path(configured).expanduser().resolve()
            if configured
            else (_repo_root() / ".tmp" / "online-safe-runtime").resolve()
        )
    configured = env.get(_LOCAL_RUNTIME_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (_backend_root() / ".sementor").resolve()


def _demo_workspace_root(env: dict[str, str]) -> Path:
    configured = env.get(_DEMO_WORKSPACE_ENV)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (_repo_root() / "deploy" / "demo-workspace").resolve()
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
