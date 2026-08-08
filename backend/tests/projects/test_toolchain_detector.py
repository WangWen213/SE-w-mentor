from __future__ import annotations

import os
from pathlib import Path

from se_mentor.projects.toolchain_detector import ToolchainKind, detect_toolchain


def test_T020_unknown_toolchain_is_reported_not_executed(tmp_path: Path) -> None:
    marker = tmp_path / "do-not-run"
    (tmp_path / "build.sh").write_text(f"echo touched > {marker}\n", encoding="utf-8")

    result = detect_toolchain(tmp_path)

    assert result.kind is ToolchainKind.UNKNOWN
    assert result.executed_commands == ()
    assert result.confidence == 0.0
    assert "no supported manifest found" in result.unknowns
    assert not marker.exists()


def test_T020_detects_python_typescript_mixed_and_limits(tmp_path: Path) -> None:
    python_repo = tmp_path / "python"
    python_repo.mkdir()
    (python_repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    py = detect_toolchain(python_repo)
    assert py.kind is ToolchainKind.PYTHON
    assert "pyproject.toml" in py.manifests
    assert "pytest" in py.test_frameworks

    ts_repo = tmp_path / "ts"
    ts_repo.mkdir()
    (ts_repo / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    ts = detect_toolchain(ts_repo)
    assert ts.kind is ToolchainKind.TYPESCRIPT
    assert "vitest" in ts.test_frameworks

    mixed_repo = tmp_path / "mixed"
    mixed_repo.mkdir()
    (mixed_repo / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (mixed_repo / "package.json").write_text("{}\n", encoding="utf-8")
    assert detect_toolchain(mixed_repo).kind is ToolchainKind.MIXED

    for index in range(3):
        (tmp_path / f"file-{index}.txt").write_text("x", encoding="utf-8")
    cwd_before = Path.cwd()
    env_before = dict(os.environ)
    limited = detect_toolchain(tmp_path, max_files=1)
    assert limited.limit_exceeded is True
    assert limited.status == "LIMIT_EXCEEDED"
    assert Path.cwd() == cwd_before
    assert dict(os.environ) == env_before
