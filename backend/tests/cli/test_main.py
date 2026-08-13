from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

import pytest

from se_mentor.application.harness import (
    CompletedRun,
    ExecutionSummary,
    GovernanceSummary,
    ImpactSummary,
    PreparedRun,
    ProjectSummary,
    ProposalSummary,
    TaskSummary,
)
from se_mentor.cli import main as cli


@dataclass
class FakeHarness:
    decision: str = "ALLOW"
    execution_status: str = "COMPLETED"
    executed: bool = False

    def prepare_run(self, *, project_path: str, task_request: str) -> PreparedRun:
        return PreparedRun(
            project=ProjectSummary(
                id="project-1",
                root_path=project_path,
                revision="abc123",
                bootstrap={"status": "READY"},
            ),
            task=TaskSummary(
                id="task-1",
                project_id="project-1",
                request=task_request,
                status="CREATED",
            ),
            proposal=ProposalSummary(
                id="proposal-1",
                task_id="task-1",
                version=1,
                goal="Improve greeting",
                understanding="Update the greeting copy",
                expected_behavior="Friendlier greeting",
                scope=("app.py",),
                changes=(
                    {"path": "app.py", "action": "update", "reason": "contains greeting"},
                ),
                steps=("read app.py", "patch greeting"),
                risks=("copy regression",),
                acceptance=("test_app.py passes",),
                validation=("pytest -q",),
                completeness="COMPLETE",
                status="DRAFT",
            ),
        )

    def confirm_and_execute(self, prepared: PreparedRun) -> CompletedRun:
        self.executed = self.decision == "ALLOW"
        execution = None
        task_status = "BLOCKED" if self.decision == "BLOCK" else "COMPLETED"
        if self.executed:
            execution = ExecutionSummary(
                task_id=prepared.task.id,
                status=self.execution_status,
                command="RUN_COMMAND",
                code=None,
                error=None,
                tools=({"name": "APPLY_PATCH", "status": "SUCCEEDED"},),
                changed_files=("app.py",),
                validation=({"command": "pytest -q", "status": "PASSED"},),
            )
        return CompletedRun(
            prepared=prepared,
            impact=ImpactSummary(
                id="impact-1",
                direct_count=1,
                indirect_count=0,
                unknown_count=0,
            ),
            governance=GovernanceSummary(
                id="decision-1",
                decision=self.decision,
                reason="Allowed within finite changed path scope.",
                approval_required=self.decision == "WARN",
                allowed_scope=("app.py",) if self.decision == "ALLOW" else (),
                denied_scope=("app.py",) if self.decision == "BLOCK" else (),
                rule_hits=(),
            ),
            execution=execution,
            task=TaskSummary(
                id=prepared.task.id,
                project_id=prepared.project.id,
                request=prepared.task.request,
                status=task_status,
            ),
        )


def test_help_exposes_serve_and_run_without_runtime_import() -> None:
    out = StringIO()

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"], stdout=out)

    assert exc.value.code == 0
    output = out.getvalue()
    assert "SE-Mentor" in output
    assert "serve" in output
    assert "run" in output
    assert "C:\\Users" not in output


def test_run_requires_project_and_task() -> None:
    err = StringIO()

    with pytest.raises(SystemExit) as exc:
        cli.main(["run"], stderr=err)

    assert exc.value.code == 2
    assert "--project" in err.getvalue()
    assert "--task" in err.getvalue()


def test_confirmation_defaults_to_cancel_and_does_not_execute() -> None:
    fake = FakeHarness()
    out = StringIO()

    code = cli.main(
        ["run", "--project", "C:\\repo", "--task", "Improve greeting"],
        stdout=out,
        input_stream=StringIO("\n"),
        app=fake,
    )

    assert code == 0
    assert "Confirm? [y/N]" in out.getvalue()
    assert "Cancelled." in out.getvalue()
    assert fake.executed is False


def test_yes_confirms_allow_and_renders_execution_summary() -> None:
    fake = FakeHarness(decision="ALLOW")
    out = StringIO()

    code = cli.main(
        ["run", "--project", "C:\\repo", "--task", "Improve greeting", "--yes"],
        stdout=out,
        app=fake,
    )

    output = out.getvalue()
    assert code == 0
    assert fake.executed is True
    assert "Decision: ALLOW" in output
    assert "APPLY_PATCH: SUCCEEDED" in output
    assert "app.py" in output


def test_governance_block_never_executes() -> None:
    fake = FakeHarness(decision="BLOCK")
    out = StringIO()

    code = cli.main(
        ["run", "--project", "C:\\repo", "--task", "Touch secrets", "--yes"],
        stdout=out,
        app=fake,
    )

    output = out.getvalue()
    assert code == 1
    assert fake.executed is False
    assert "Decision: BLOCK" in output
    assert "Status: NOT_EXECUTED" in output

