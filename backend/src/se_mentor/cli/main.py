from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from se_mentor.application.harness import CompletedRun, HarnessApplication, PreparedRun

APP_DESCRIPTION = """SE-Mentor

Commands:

serve
    Start the local SE-Mentor WebUI/server.

run
    Run a task through the SE-Mentor Agent Harness.

credentials
    Manage local LLM credentials.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="se-mentor.exe",
        description=APP_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "serve",
        help="Start the local SE-Mentor WebUI/server.",
        description="Start the local SE-Mentor WebUI/server.",
    )
    run_parser = subparsers.add_parser(
        "run",
        help="Run a task through the SE-Mentor Agent Harness.",
        description="Run a task through the SE-Mentor Agent Harness.",
    )
    run_parser.add_argument("--project", required=True, help="Git repository root to open.")
    run_parser.add_argument("--task", required=True, help="Task request to run.")
    run_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the generated proposal without an interactive prompt.",
    )

    credentials_parser = subparsers.add_parser(
        "credentials",
        help="Manage local LLM credentials.",
        description="Manage local LLM credentials.",
    )
    credential_subparsers = credentials_parser.add_subparsers(dest="credentials_command")
    credential_subparsers.add_parser("status", help="Show credential configuration status.")
    set_parser = credential_subparsers.add_parser("set", help="Store an LLM API key.")
    set_parser.add_argument("--key", help="API key value. Omit to enter it securely.")
    update_parser = credential_subparsers.add_parser(
        "update",
        help="Replace the stored LLM API key.",
    )
    update_parser.add_argument("--key", help="API key value. Omit to enter it securely.")
    credential_subparsers.add_parser("clear", help="Remove the stored LLM API key.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    input_stream: TextIO | None = None,
    app: HarnessApplication | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = build_parser()
    with redirect_stdout(out), redirect_stderr(err):
        args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "serve":
        parser.print_help(out)
        return 0
    try:
        if args.command == "run":
            return _run(args, out=out, input_stream=input_stream or sys.stdin, app=app)
        if args.command == "credentials":
            return _credentials(args, out=out)
    except KeyboardInterrupt:
        print("Cancelled.", file=err)
        return 1
    except Exception as exc:
        code = getattr(exc, "code", "CLI_FAILED")
        if code != "CLI_FAILED":
            print(f"{code}: {exc}", file=err)
            return 1
        print(f"CLI_FAILED: {exc}", file=err)
        return 1
    parser.print_help(out)
    return 2


def _run(
    args,
    *,
    out: TextIO,
    input_stream: TextIO,
    app: HarnessApplication | None,
) -> int:
    from se_mentor.application.harness import HarnessApplication

    harness = app or HarnessApplication()
    prepared = harness.prepare_run(project_path=args.project, task_request=args.task)
    _render_prepared(prepared, out=out)
    if not args.yes and not _confirm(input_stream=input_stream, out=out):
        print("Cancelled.", file=out)
        return 0
    completed = harness.confirm_and_execute(prepared)
    _render_completed(completed, out=out)
    if completed.governance.decision == "BLOCK":
        return 1
    if completed.governance.decision == "WARN":
        return 1
    if completed.execution is None:
        return 1
    return 0 if completed.execution.status == "COMPLETED" else 1


def _credentials(args, *, out: TextIO) -> int:
    from se_mentor.api.runtime import get_credential_store
    from se_mentor.cli.credentials import (
        clear_credential,
        credential_status,
        set_credential,
        update_credential,
    )

    store = get_credential_store()
    command = args.credentials_command or "status"
    if command == "status":
        result = credential_status(store)
        _render_credential_status(result.status, out=out)
        return 0
    if command == "clear":
        clear_credential(store)
        print("Credentials cleared.", file=out)
        return 0
    if command in {"set", "update"}:
        value = args.key or getpass.getpass("API key: ")
        if not value.strip():
            print("API key is required.", file=out)
            return 2
        if command == "set":
            set_credential(store, value)
            print("Credentials saved.", file=out)
        else:
            update_credential(store, value)
            print("Credentials updated.", file=out)
        return 0
    print("Unknown credentials command.", file=out)
    return 2


def _render_prepared(prepared: PreparedRun, *, out: TextIO) -> None:
    proposal = prepared.proposal
    print("Project", file=out)
    print("=======", file=out)
    print(f"Root: {prepared.project.root_path}", file=out)
    print(f"Project ID: {prepared.project.id}", file=out)
    print(f"Task ID: {prepared.task.id}", file=out)
    print("", file=out)
    print("Proposal", file=out)
    print("========", file=out)
    print(f"Goal: {proposal.goal}", file=out)
    print(f"Understanding: {proposal.understanding}", file=out)
    print(f"Expected behavior: {proposal.expected_behavior}", file=out)
    _print_items("Files / Scope", proposal.scope, out=out)
    if proposal.changes:
        print("Changes:", file=out)
        for change in proposal.changes:
            path = change.get("path") or "<unknown>"
            action = change.get("action") or "update"
            reason = change.get("reason") or ""
            print(f"  - {path}: {action} - {reason}", file=out)
    _print_items("Plan", proposal.steps, out=out)
    _print_items("Risks", proposal.risks, out=out)
    _print_items("Validation", proposal.validation or proposal.acceptance, out=out)
    print("", file=out)


def _render_completed(completed: CompletedRun, *, out: TextIO) -> None:
    impact = completed.impact
    governance = completed.governance
    print("", file=out)
    print("Impact", file=out)
    print("======", file=out)
    print(f"Direct impacts: {impact.direct_count}", file=out)
    print(f"Indirect impacts: {impact.indirect_count}", file=out)
    print(f"Unknowns: {impact.unknown_count}", file=out)
    print("", file=out)
    print("Governance", file=out)
    print("==========", file=out)
    print(f"Decision: {governance.decision}", file=out)
    print(f"Approval required: {governance.approval_required}", file=out)
    print(f"Reason: {governance.reason}", file=out)
    _print_items("Allowed scope", governance.allowed_scope, out=out)
    _print_items("Denied scope", governance.denied_scope, out=out)
    if completed.execution is None:
        print("", file=out)
        print("Execution", file=out)
        print("=========", file=out)
        print("Status: NOT_EXECUTED", file=out)
        print(f"Task status: {completed.task.status}", file=out)
        return
    execution = completed.execution
    print("", file=out)
    print("Execution", file=out)
    print("=========", file=out)
    print(f"Status: {execution.status}", file=out)
    if execution.code:
        print(f"Code: {execution.code}", file=out)
    if execution.error:
        print(f"Error: {execution.error}", file=out)
    if execution.tools:
        print("Tools:", file=out)
        for tool in execution.tools:
            print(f"  - {tool['name']}: {tool['status']}", file=out)
    _print_items("Changed files", execution.changed_files, out=out)
    if execution.validation:
        print("Validation:", file=out)
        for run in execution.validation:
            print(f"  - {run['command']}: {run['status']}", file=out)
    print(f"Task status: {completed.task.status}", file=out)


def _render_credential_status(status, *, out: TextIO) -> None:
    from se_mentor.api.runtime import credential_status_payload

    payload = credential_status_payload(status)
    print("Credentials", file=out)
    print("===========", file=out)
    print(f"Configured: {payload['configured']}", file=out)
    print(f"Provider: {payload['provider']}", file=out)
    print(f"Source: {payload['source']}", file=out)
    if payload.get("baseUrl"):
        print(f"Base URL: {payload['baseUrl']}", file=out)
    if payload.get("model"):
        print(f"Model: {payload['model']}", file=out)


def _confirm(*, input_stream: TextIO, out: TextIO) -> bool:
    print("Confirm? [y/N] ", end="", flush=True, file=out)
    answer = input_stream.readline().strip().lower()
    return answer in {"y", "yes"}


def _print_items(label: str, items: Sequence[object], *, out: TextIO) -> None:
    if not items:
        return
    print(f"{label}:", file=out)
    for item in items:
        print(f"  - {item}", file=out)


if __name__ == "__main__":
    raise SystemExit(main())
