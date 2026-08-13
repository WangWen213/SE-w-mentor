from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_launcher_dispatch_preserves_default_serve_and_adds_cli_commands() -> None:
    launcher = read("packaging/se_mentor_launcher.py")
    assert "return serve()" in launcher
    assert "args[0] == \"serve\"" in launcher
    assert "\"run\"" in launcher
    assert "\"credentials\"" in launcher
    assert "se_mentor.cli.main" in launcher
    assert "uvicorn.run" in launcher


def test_pyinstaller_spec_collects_cli_and_application_facade() -> None:
    spec = read("packaging/se-mentor.spec")
    assert '"se_mentor.application.harness"' in spec
    assert '"se_mentor.cli.main"' in spec
    assert "console=True" in spec
    assert "deploy/demo-workspace" in spec


def test_cli_facade_uses_existing_harness_services_without_direct_tool_bypass() -> None:
    facade = read("backend/src/se_mentor/application/harness.py")
    assert "register_project(" in facade
    assert "ProjectBootstrapService" in facade
    assert "TaskService" in facade
    assert "ProposalContextBuilder" in facade
    assert "ProposalGenerator" in facade
    assert "ChangeFlowOrchestrator" in facade
    assert "ExecutionOrchestrator" in facade
    assert "AtomicApplyPatchTool" not in facade
    assert "ToolDispatcher" not in facade
    assert "sqlite3.connect" not in facade

