from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationCommand:
    check_name: str
    program: str
    args: tuple[str, ...]
    required: bool = True


def command_for_check(check_name: str) -> ValidationCommand:
    if check_name == "unit":
        return ValidationCommand(check_name, "pytest", ("-q",))
    if check_name == "contract":
        return ValidationCommand(check_name, "pytest", ("backend/tests/contracts", "-q"))
    if check_name.startswith("migration"):
        return ValidationCommand(check_name, "alembic", ("heads",))
    return ValidationCommand(check_name, check_name, ())
