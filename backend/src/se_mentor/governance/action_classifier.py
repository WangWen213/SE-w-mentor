from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from se_mentor.security.path_policy import PathPolicy


class ActionRisk(StrEnum):
    SAFE = "SAFE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY_HARD = "DENY_HARD"


@dataclass(frozen=True)
class ActionClassification:
    risk: ActionRisk
    category: str
    reasons: tuple[str, ...]


class ActionClassifier:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.path_policy = PathPolicy(self.project_root)

    def classify_path_write(self, relative_path: str) -> ActionClassification:
        path = Path(relative_path)
        lowered = relative_path.lower()
        if path.is_absolute() or ".." in path.parts:
            return ActionClassification(ActionRisk.DENY_HARD, "OUTSIDE_PATH", ("outside path",))
        if any(token in lowered for token in (".env", "secret", "token", "password", "credential")):
            return ActionClassification(
                ActionRisk.DENY_HARD, "CREDENTIAL_SENSITIVE", ("credential",)
            )
        return ActionClassification(ActionRisk.SAFE, "SAFE", ("path",))

    def classify_command(self, command: str) -> ActionClassification:
        lowered = command.lower()
        if "|| true" in lowered or " 2>nul" in lowered:
            return ActionClassification(
                ActionRisk.REQUIRE_APPROVAL,
                "VALIDATION_EVASION",
                ("suppresses validation failure",),
            )
        if _is_recursive_delete(lowered):
            return ActionClassification(
                ActionRisk.DENY_HARD, "RECURSIVE_DELETE", ("recursive delete",)
            )
        if any(token in lowered for token in ("npm install", "pip install", "poetry add")):
            return ActionClassification(ActionRisk.REQUIRE_APPROVAL, "DEPENDENCY", ("dependency",))
        if any(token in lowered for token in ("alembic revision", "migrate", "prisma migrate")):
            return ActionClassification(ActionRisk.REQUIRE_APPROVAL, "SCHEMA", ("schema",))
        if any(token in lowered for token in ("deploy", "kubectl apply", "terraform apply")):
            return ActionClassification(ActionRisk.REQUIRE_APPROVAL, "DEPLOYMENT", ("deployment",))
        if lowered.startswith("pytest") and (" -k " in lowered or "::" in lowered):
            return ActionClassification(
                ActionRisk.REQUIRE_APPROVAL,
                "VALIDATION_EVASION",
                ("validation scope narrowed",),
            )
        if lowered.startswith("pytest"):
            return ActionClassification(ActionRisk.SAFE, "SAFE", ("pytest",))
        if lowered.startswith("ruff"):
            return ActionClassification(ActionRisk.SAFE, "SAFE", ("ruff",))
        if any(token in lowered for token in ("powershell", "cmd /c", "bash -lc")):
            return ActionClassification(ActionRisk.REQUIRE_APPROVAL, "SHELL", ("shell",))
        return ActionClassification(ActionRisk.SAFE, "SAFE", ("default",))

    def classify_patch(self, patch_text: str) -> ActionClassification:
        lowered = patch_text.lower()
        if "- assert" in lowered or "+ pytestmark = pytest.mark.skip" in lowered:
            return ActionClassification(
                ActionRisk.REQUIRE_APPROVAL,
                "VALIDATION_EVASION",
                ("validation semantics changed",),
            )
        if "skip(" in lowered and lowered.count("+") > 0:
            return ActionClassification(
                ActionRisk.REQUIRE_APPROVAL,
                "VALIDATION_EVASION",
                ("test skip introduced",),
            )
        return ActionClassification(ActionRisk.SAFE, "SAFE", ("patch",))


def _is_recursive_delete(command: str) -> bool:
    return (
        "rm -rf" in command
        or "rm -fr" in command
        or "remove-item -recurse" in command
        or "del /s" in command
        or "rmdir /s" in command
    )
