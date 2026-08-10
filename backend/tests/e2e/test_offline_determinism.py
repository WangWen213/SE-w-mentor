from __future__ import annotations

import socket

from scripts.run_offline_e2e import run_repeated


def test_T085_mock_harness_makes_zero_network_calls_and_is_deterministic(monkeypatch) -> None:
    network_calls: list[str] = []

    def blocked_socket(*args, **kwargs):
        network_calls.append("socket")
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked_socket)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-key-must-not-be-used")

    result = run_repeated(repetitions=5)

    assert network_calls == []
    assert result.network_calls == 0
    assert result.used_secret_env_keys == ()
    assert len(result.timeline_hashes) == 5
    assert len(set(result.timeline_hashes)) == 1
    assert result.timeline_hashes[0]
