from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_T105_packaging_files_exist() -> None:
    assert (ROOT / "packaging" / "se-mentor.spec").is_file()
    assert (ROOT / "packaging" / "se_mentor_launcher.py").is_file()
    assert (ROOT / "scripts" / "build_windows.ps1").is_file()
    assert (ROOT / "scripts" / "smoke_windows.ps1").is_file()
    assert (ROOT / "evidence" / "windows-package" / ".gitkeep").is_file()


def test_T105_pyinstaller_spec_is_onedir_and_collects_required_resources() -> None:
    spec = read("packaging/se-mentor.spec")
    assert "COLLECT(" in spec
    assert "--onefile" not in spec
    assert "frontend" in spec
    assert "migrations" in spec
    assert "alembic.ini" in spec
    assert "deploy/demo-workspace" in spec
    assert ".sementor" not in spec
    assert '(str(ROOT / "frontend")' not in spec


def test_T105_launcher_uses_localhost_runtime_migrations_and_static_frontend() -> None:
    launcher = read("packaging/se_mentor_launcher.py")
    assert "127.0.0.1" in launcher
    assert "0.0.0.0" not in launcher
    assert "SE_MENTOR_DATABASE_URL" in launcher
    assert "SE_MENTOR_RUNTIME_ROOT" in launcher
    assert "command.upgrade" in launcher
    assert "StaticFiles" in launcher
    assert "uvicorn.run" in launcher


def test_T105_build_and_smoke_scripts_fail_closed() -> None:
    combined = read("scripts/build_windows.ps1") + read("scripts/smoke_windows.ps1")
    assert '$ErrorActionPreference = "Stop"' in combined
    assert "|| true" not in combined
    assert "git clean" not in combined
    assert "git reset" not in combined
    assert "taskkill /IM python.exe" not in combined
    assert "npm.cmd" in combined
    assert 'Invoke-Checked $Npm @("ci")' in combined
    assert 'Invoke-Checked $Npm @("run", "build")' in combined
    assert "frontend-build" in combined
    assert "vite.config.mjs" in combined
    assert "LASTEXITCODE" in combined
    assert "PyInstaller" in combined


def test_T105_distribution_manifest_excludes_secret_runtime_data() -> None:
    smoke = read("scripts/smoke_windows.ps1")
    for forbidden in (
        "\\.env$",
        "\\.pem$",
        "\\.key$",
        "\\.sqlite3$",
        "perf-runtime\\.log$",
        "backups?",
        "credentials?",
        "secrets?",
    ):
        assert forbidden in smoke
    assert "sk-[A-Za-z0-9_-]{20,}" in smoke
    assert "PRIVATE KEY" in smoke
