from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path
from types import ModuleType

import pytest


def test_T085_mock_harness_makes_zero_network_calls_and_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_calls: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> None:
        network_calls.append("socket")
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked_socket)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-key-must-not-be-used")

    run_repeated = _offline_runner().__dict__["run_repeated"]
    result = run_repeated(repetitions=5)

    assert network_calls == []
    assert result.network_calls == 0
    assert result.used_secret_env_keys == ()
    assert len(result.timeline_hashes) == 5
    assert len(set(result.timeline_hashes)) == 1
    assert result.timeline_hashes[0]


def _offline_runner() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "run_offline_e2e.py"
    spec = importlib.util.spec_from_file_location("run_offline_e2e", script)
    if spec is None or spec.loader is None:
        raise AssertionError("offline runner spec missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
