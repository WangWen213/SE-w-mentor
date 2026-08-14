from __future__ import annotations

import json

from se_mentor.demo import harness_demo


def test_T113_demo_scenarios_are_repeatable_and_match_expected_outcomes() -> None:
    first = harness_demo.run_demo(all_scenarios=True)
    second = harness_demo.run_demo(all_scenarios=True)

    assert first.passed is True
    assert second.passed is True
    assert [result.scenario for result in first.results] == ["governance", "feedback", "memory"]
    assert [result.passed for result in first.results] == [True, True, True]
    assert [result.passed for result in second.results] == [True, True, True]
    governance = first.results[0].evidence
    feedback = first.results[1].evidence
    memory = first.results[2].evidence
    assert governance["governance_decision"] == "BLOCK"
    assert governance["tool_executed"] is False
    assert feedback["first_validation"] == "FAIL"
    assert feedback["feedback_in_next_provider_context"] is True
    assert feedback["action_changed"] is True
    assert feedback["second_validation"] == "PASS"
    assert memory["retrieval_result"] == "HIT"
    assert memory["provider_received_memory"] is True
    assert memory["behavior_affected"] is True


def test_T113_demo_output_writes_parseable_secret_free_evidence(tmp_path) -> None:
    result = harness_demo.run_demo(all_scenarios=True, output=tmp_path)

    assert result.passed is True
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["scenarios_passed"] == 3
    assert summary["offline"] is True
    assert summary["mock_provider_only"] is True
    assert summary["network_calls"] == 0
    assert summary["real_api_key_required"] is False
    assert summary["credential_manager_accessed"] is False
    for name in harness_demo.SCENARIO_ORDER:
        payload = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
        assert payload["passed"] is True
    combined = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert "sk-" not in combined
    assert "password" not in combined.lower()


def test_T113_cli_returns_nonzero_when_any_scenario_fails(monkeypatch) -> None:
    def fail_governance(*, verbose: bool) -> harness_demo.ScenarioResult:
        raise harness_demo.DemoAssertionError("forced", "PASS", "FAIL")

    monkeypatch.setitem(harness_demo._SCENARIOS, "governance", fail_governance)

    assert harness_demo.main(["--scenario", "governance"]) == 1
