from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from se_mentor.indexing.file_inventory import build_file_inventory


def _init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)


def test_T028_dotenv_binary_large_and_symlink_escape_are_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / "binary.bin").write_bytes(b"\x00\x01\x02")
    (repo / "backup.py~").write_text("old\n", encoding="utf-8")
    (repo / "large.txt").write_text("x" * 20, encoding="utf-8")
    (repo / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("escape\n", encoding="utf-8")
    link = repo / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not available in this environment")

    inventory = build_file_inventory(repo, max_file_size_bytes=10, max_files=20)
    included = {entry.relative_path for entry in inventory.files}
    excluded = {entry.relative_path: entry.reason for entry in inventory.excluded}

    assert "app.py" in included
    assert ".env" in excluded
    assert excluded["binary.bin"] == "BINARY_FILE"
    assert excluded["backup.py~"] == "BACKUP_FILE"
    assert excluded["large.txt"] == "FILE_TOO_LARGE"
    assert excluded["ignored.txt"] == "GIT_IGNORED"
    assert excluded["escape.txt"] == "REALPATH_OUTSIDE_PROJECT"
    app = next(entry for entry in inventory.files if entry.relative_path == "app.py")
    assert len(app.sha256) == 64
    assert app.git_status in {"UNTRACKED", "CLEAN", "MODIFIED"}

    for index in range(3):
        (repo / f"extra-{index}.txt").write_text("x", encoding="utf-8")
    limited = build_file_inventory(repo, max_files=1)
    assert limited.limit_status == "FILE_COUNT_LIMIT"
    assert os.getcwd()
