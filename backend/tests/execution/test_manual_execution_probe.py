from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from manual_execution_probe import run_probe


def test_manual_execution_probe_proves_real_harness_write(tmp_path: Path) -> None:
    result = run_probe(tmp_path)

    assert result["status"] == "PASS"
    assert result["first_broken_stage"] is None
    assert result["transaction_id"]
    assert result["workspace"]["app_txt"] == "TASK1\n"
    assert result["git_diff"].strip()
    assert any(
        item["tool_name"] == "APPLY_PATCH" and item["status"] == "SUCCEEDED"
        for item in result["ToolExecutions"]
    )
    assert any(item["before_hash"] != item["after_hash"] for item in result["FileChanges"])
