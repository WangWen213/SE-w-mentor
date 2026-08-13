from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from stat import S_IWRITE


DEMO_BASELINE_DIRNAME = ".baseline"


class DemoRuntimeError(RuntimeError):
    pass


def ensure_demo_workspace(workspace_root: str | Path) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    baseline = root / DEMO_BASELINE_DIRNAME
    if not baseline.is_dir():
        raise DemoRuntimeError("demo workspace baseline is missing")
    reset_demo_workspace(root)
    return root


def reset_demo_workspace(workspace_root: str | Path) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    baseline = root / DEMO_BASELINE_DIRNAME
    if not baseline.is_dir():
        raise DemoRuntimeError("demo workspace baseline is missing")
    if root.name != "demo-workspace":
        raise DemoRuntimeError("demo reset requires an explicit demo-workspace root")
    root.mkdir(parents=True, exist_ok=True)
    for item in root.iterdir():
        if item.name in {DEMO_BASELINE_DIRNAME, ".gitignore"}:
            continue
        if item.is_dir():
            shutil.rmtree(item, onexc=_make_writable)
        else:
            item.chmod(S_IWRITE)
            item.unlink()
    _copy_baseline(baseline, root)
    _ensure_git_repository(root)
    return root


def reset_demo_runtime(runtime_root: str | Path, *, demo_workspace_root: str | Path) -> None:
    root = Path(runtime_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("se_mentor_api.sqlite3", "se_mentor_api.sqlite3-shm", "se_mentor_api.sqlite3-wal"):
        target = root / name
        if target.exists():
            target.unlink()
    reset_demo_workspace(demo_workspace_root)


def _copy_baseline(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _ensure_git_repository(root: Path) -> None:
    if not (root / ".git").exists():
        _git(root, "init")
        _git(root, "config", "user.email", "demo@example.invalid")
        _git(root, "config", "user.name", "SE-Mentor Demo")
    _git(root, "add", ".")
    _git(root, "commit", "--allow-empty", "-m", "demo baseline")


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise DemoRuntimeError("demo workspace git reset failed")


def _make_writable(function, path, _exc_info) -> None:
    target = Path(path)
    try:
        target.chmod(S_IWRITE)
    except OSError:
        pass
    function(path)
