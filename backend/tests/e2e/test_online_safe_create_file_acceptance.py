from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_online_safe_create_file_full_path_acceptance() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/accept_online_safe_create_file_e2e.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == "PASS"
    assert payload["authorized_target"] == "src/sample/text_utils.py"
    assert "src/sample/text_utils.py" in payload["git_status"]
    assert "outside_policy" in payload["denied_error"]
