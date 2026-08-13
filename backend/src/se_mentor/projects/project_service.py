from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from se_mentor.models.project import Project
from se_mentor.projects.project_repository import add_project, find_project_by_root


class ProjectRegistrationError(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredProject:
    project: Project
    current_revision: str


def register_project(
    session: Session,
    root_path: str | Path,
    *,
    authorized_root: str | Path,
) -> RegisteredProject:
    root = Path(root_path).expanduser()
    authorized = Path(authorized_root).expanduser()
    if not root.exists():
        raise ProjectRegistrationError("project path does not exist")
    real_root = root.resolve(strict=True)
    real_authorized = authorized.resolve(strict=True)
    if not _is_relative_to(real_root, real_authorized):
        raise ProjectRegistrationError("project path is outside authorized root")
    if find_project_by_root(session, real_root) is not None:
        raise ProjectRegistrationError("duplicate project registration")

    _git(real_root, "rev-parse", "--show-toplevel")
    inside = _git(real_root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise ProjectRegistrationError("path is not inside a Git work tree")
    toplevel = Path(_git(real_root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if toplevel != real_root:
        raise ProjectRegistrationError("registered path must be the Git repository root")
    revision = _git(real_root, "rev-parse", "HEAD")

    return RegisteredProject(project=add_project(session, real_root), current_revision=revision)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={cwd.as_posix()}", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ProjectRegistrationError("path is not a valid Git repository")
    return result.stdout.strip()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
