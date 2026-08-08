from __future__ import annotations

from se_mentor.governance.action_classifier import (
    ActionClassification,
    ActionClassifier,
    ActionRisk,
)


def test_T045_outside_path_recursive_delete_and_validation_bypass_are_deny_or_warn() -> None:
    classifier = ActionClassifier(project_root="C:/repo")

    cases = {
        "outside": classifier.classify_path_write("../secret.txt"),
        "recursive_delete": classifier.classify_command("rm -rf src"),
        "powershell_delete": classifier.classify_command("Remove-Item -Recurse src"),
        "credential": classifier.classify_path_write(".env"),
        "dangerous_shell": classifier.classify_command("pytest || true"),
        "dependency": classifier.classify_command("npm install left-pad"),
        "schema": classifier.classify_command("alembic revision --autogenerate"),
        "deploy": classifier.classify_command("vercel deploy --prod"),
        "delete_assert": classifier.classify_patch("- assert user.is_admin\n+ pass\n"),
        "batch_skip": classifier.classify_patch("+ pytestmark = pytest.mark.skip\n"),
        "scope_shrink": classifier.classify_command("pytest backend/tests/test_one.py -k smoke"),
        "normal_pytest": classifier.classify_command("pytest backend/tests -q"),
        "normal_ruff": classifier.classify_command("ruff check backend/src"),
    }

    assert cases["outside"].risk is ActionRisk.DENY_HARD
    assert cases["recursive_delete"].risk is ActionRisk.DENY_HARD
    assert cases["powershell_delete"].risk is ActionRisk.DENY_HARD
    assert cases["credential"].risk is ActionRisk.DENY_HARD
    assert cases["dangerous_shell"].risk is ActionRisk.REQUIRE_APPROVAL
    assert cases["dependency"].risk is ActionRisk.REQUIRE_APPROVAL
    assert cases["schema"].risk is ActionRisk.REQUIRE_APPROVAL
    assert cases["deploy"].risk is ActionRisk.REQUIRE_APPROVAL
    assert cases["delete_assert"].category == "VALIDATION_EVASION"
    assert cases["batch_skip"].category == "VALIDATION_EVASION"
    assert cases["scope_shrink"].category == "VALIDATION_EVASION"
    assert cases["normal_pytest"] == ActionClassification(ActionRisk.SAFE, "SAFE", ("pytest",))
    assert cases["normal_ruff"] == ActionClassification(ActionRisk.SAFE, "SAFE", ("ruff",))
