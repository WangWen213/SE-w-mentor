from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.api.runtime import get_domain_provider, get_runtime_settings, get_session_factory
from se_mentor.api.workbench_presentation import workbench_message_text
from se_mentor.db.session import session_scope
from se_mentor.execution.orchestrator import ExecutionOrchestrator, ExecutionResult
from se_mentor.git.git_service import GitService
from se_mentor.llm.base import LLMRequest
from se_mentor.models.execution import FileChange, ToolExecution
from se_mentor.models.governance import GovernanceDecision, GovernanceVerdict, ImpactReport
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
)
from se_mentor.models.validation import ValidationPlan, ValidationRun
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.orchestration.change_flow import ChangeFlowOrchestrator
from se_mentor.projects.bootstrap import ProjectBootstrapService
from se_mentor.projects.project_repository import find_project_by_root
from se_mentor.projects.project_service import ProjectRegistrationError, register_project
from se_mentor.proposals.context import ProposalContextBuilder
from se_mentor.proposals.generator import ProposalGenerator
from se_mentor.proposals.supplement import run_bounded_technical_supplement
from se_mentor.runtime.demo import DemoRuntimeError, ensure_demo_workspace
from se_mentor.runtime.profiles import RuntimeProfile
from se_mentor.tasks.task_service import TaskCreationRequest, TaskService

DEFAULT_ACTOR_ID = "cli-user"
DEFAULT_EXECUTION_COMMAND = "RUN_COMMAND"
DEFAULT_TOKEN_BUDGET = 8192


class HarnessError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    root_path: str
    revision: str | None
    bootstrap: dict[str, object]


@dataclass(frozen=True)
class TaskSummary:
    id: str
    project_id: str
    request: str
    status: str


@dataclass(frozen=True)
class ProposalSummary:
    id: str
    task_id: str
    version: int
    goal: str
    understanding: str
    expected_behavior: str
    scope: tuple[str, ...]
    changes: tuple[dict[str, object], ...]
    steps: tuple[str, ...]
    risks: tuple[str, ...]
    acceptance: tuple[str, ...]
    validation: tuple[str, ...]
    completeness: str
    status: str


@dataclass(frozen=True)
class PreparedRun:
    project: ProjectSummary
    task: TaskSummary
    proposal: ProposalSummary


@dataclass(frozen=True)
class ImpactSummary:
    id: str
    direct_count: int
    indirect_count: int
    unknown_count: int


@dataclass(frozen=True)
class GovernanceSummary:
    id: str
    decision: str
    reason: str
    approval_required: bool
    allowed_scope: tuple[str, ...]
    denied_scope: tuple[str, ...]
    rule_hits: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ExecutionSummary:
    task_id: str
    status: str
    command: str | None
    code: str | None
    error: str | None
    tools: tuple[dict[str, object], ...]
    changed_files: tuple[str, ...]
    validation: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class CompletedRun:
    prepared: PreparedRun
    impact: ImpactSummary
    governance: GovernanceSummary
    execution: ExecutionSummary | None
    task: TaskSummary


class HarnessApplication:
    """Thin application facade used by non-HTTP adapters."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        *,
        actor_id: str = DEFAULT_ACTOR_ID,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.actor_id = actor_id

    def prepare_run(self, *, project_path: str | Path, task_request: str) -> PreparedRun:
        request = task_request.strip()
        if not request:
            raise HarnessError("TASK_REQUEST_REQUIRED", "task request is required")
        project = self.open_project(project_path)
        task = self.create_task(project.id, request)
        proposal = self.generate_proposal(task.id, request)
        return PreparedRun(project=project, task=task, proposal=proposal)

    def confirm_and_execute(
        self,
        prepared: PreparedRun,
        *,
        command: str = DEFAULT_EXECUTION_COMMAND,
    ) -> CompletedRun:
        with session_scope(self.session_factory) as session:
            started = perf_counter()
            result = ChangeFlowOrchestrator(session, get_domain_provider()).confirm_and_analyze(
                prepared.proposal.id,
                actor_id=self.actor_id,
            )
            decision = _governance_summary(result.governance_decision)
            impact = _impact_summary(result.impact_report)
            _ = int((perf_counter() - started) * 1000)

        execution = None
        if decision.decision == GovernanceVerdict.ALLOW:
            execution_result = ExecutionOrchestrator(self.session_factory).execute_task(
                prepared.task.id,
                command=command,
            )
            execution = self.execution_summary(prepared.task.id, execution_result)
        task = self.task_summary(prepared.task.id)
        return CompletedRun(
            prepared=prepared,
            impact=impact,
            governance=decision,
            execution=execution,
            task=task,
        )

    def open_project(self, project_path: str | Path) -> ProjectSummary:
        root_path = self._resolved_project_path(project_path)
        try:
            with session_scope(self.session_factory) as session:
                registered = register_project(
                    session,
                    root_path,
                    authorized_root=Path(root_path).expanduser(),
                )
                project_id = registered.project.id
                revision = registered.current_revision
        except ProjectRegistrationError as exc:
            if "duplicate" not in str(exc):
                raise HarnessError("PROJECT_REGISTRATION_FAILED", str(exc)) from exc
            with session_scope(self.session_factory) as session:
                existing = find_project_by_root(session, Path(root_path).resolve(strict=True))
                if existing is None:
                    raise HarnessError("PROJECT_REGISTRATION_FAILED", str(exc)) from exc
                existing.updated_at = datetime.now(UTC)
                session.flush()
                project_id = existing.id
                revision = _quick_revision(existing.root_path)
        except (OSError, DemoRuntimeError) as exc:
            raise HarnessError(
                "CLOUD_DEMO_PROJECT_RESTRICTED",
                "demo mode only allows the predefined demo workspace",
            ) from exc

        bootstrap = self._bootstrap_project(project_id)
        with session_scope(self.session_factory) as session:
            project = session.get(Project, project_id)
            if project is None:
                raise HarnessError("PROJECT_NOT_FOUND", "project not found")
            return ProjectSummary(
                id=project.id,
                root_path=project.root_path,
                revision=revision,
                bootstrap=bootstrap,
            )

    def create_task(self, project_id: str, request: str) -> TaskSummary:
        with session_scope(self.session_factory) as session:
            project = session.get(Project, project_id)
            if project is None:
                raise HarnessError("PROJECT_NOT_FOUND", "project not found")
            try:
                base_revision = GitService(project.root_path).base_revision()
            except Exception as exc:
                raise HarnessError("TASK_CREATE_FAILED", str(exc)) from exc
        try:
            result = TaskService(self.session_factory).create_task(
                TaskCreationRequest(
                    project_id=project_id,
                    original_request=request,
                    requester_id=self.actor_id,
                    base_revision=base_revision,
                    token_budget=DEFAULT_TOKEN_BUDGET,
                ),
                actor_id=self.actor_id,
                idempotency_key=f"task-create:{uuid4()}",
            )
        except ValueError as exc:
            raise HarnessError("TASK_CREATE_FAILED", str(exc)) from exc
        with session_scope(self.session_factory) as session:
            task = session.get(ChangeTask, result.task_id)
            if task is None:
                raise HarnessError("TASK_NOT_FOUND", "task not found")
            _add_workbench_message(
                session,
                task_id=task.id,
                role="USER",
                kind="TEXT",
                status="DONE",
                text=task.original_request,
            )
            return _task_summary(task)

    def generate_proposal(self, task_id: str, goal: str) -> ProposalSummary:
        with session_scope(self.session_factory) as session:
            task = session.get(ChangeTask, task_id)
            if task is None:
                raise HarnessError("TASK_NOT_FOUND", "task not found")
            self._ensure_project_context_ready(session, task.project_id)
            context = ProposalContextBuilder(session).build_for_task(task_id, goal)
            generator = ProposalGenerator(session, get_domain_provider())
            proposal = generator.generate(
                task_id=task_id,
                request=LLMRequest(
                    prompt_summary="structured change proposal",
                    input_text=goal,
                ),
                context_package=context.context_package,
                evidenced_paths=context.evidenced_paths,
            )
            if proposal.completeness == ProposalCompleteness.INCOMPLETE:
                proposal = run_bounded_technical_supplement(
                    session,
                    generator,
                    task,
                    proposal,
                    context,
                )
            _add_workbench_message(
                session,
                task_id=task_id,
                role="MENTOR",
                kind="PROPOSAL",
                status="DONE",
                text=_proposal_message_text(proposal),
                proposal_id=proposal.id,
            )
            return _proposal_summary(proposal)

    def task_summary(self, task_id: str) -> TaskSummary:
        with session_scope(self.session_factory) as session:
            task = session.get(ChangeTask, task_id)
            if task is None:
                raise HarnessError("TASK_NOT_FOUND", "task not found")
            return _task_summary(task)

    def execution_summary(
        self,
        task_id: str,
        result: ExecutionResult | None = None,
    ) -> ExecutionSummary:
        with session_scope(self.session_factory) as session:
            tools = [
                {
                    "name": tool.tool_name,
                    "status": tool.status,
                    "command": tool.command_summary,
                    "exitCode": tool.exit_code,
                }
                for tool in session.scalars(
                    select(ToolExecution)
                    .where(ToolExecution.task_id == task_id)
                    .order_by(ToolExecution.created_at, ToolExecution.id)
                ).all()
            ]
            changes = tuple(
                str(row[0])
                for row in session.execute(
                    select(FileChange.relative_path)
                    .where(FileChange.task_id == task_id)
                    .order_by(FileChange.created_at, FileChange.id)
                )
            )
            validation = [
                {
                    "command": run.command_summary,
                    "status": run.status,
                    "exitCode": run.exit_code,
                }
                for run in session.scalars(
                    select(ValidationRun)
                    .join(ValidationPlan, ValidationRun.validation_plan_id == ValidationPlan.id)
                    .where(ValidationPlan.task_id == task_id)
                    .order_by(ValidationRun.created_at, ValidationRun.id)
                ).all()
            ]
        return ExecutionSummary(
            task_id=task_id,
            status=result.status if result else "NOT_EXECUTED",
            command=result.command if result else None,
            code=result.code if result else None,
            error=result.error if result else None,
            tools=tuple(tools),
            changed_files=changes,
            validation=tuple(validation),
        )

    def _bootstrap_project(self, project_id: str) -> dict[str, object]:
        with session_scope(self.session_factory) as session:
            bootstrap = ProjectBootstrapService(session).bootstrap(project_id)
            return {
                "status": "READY",
                "readiness": {
                    "projectUnderstanding": True,
                    "fileInventory": {
                        "files": bootstrap.file_count,
                        "excluded": bootstrap.excluded_count,
                    },
                    "codeIndex": {
                        "symbols": bootstrap.symbol_count,
                        "relations": bootstrap.relation_count,
                    },
                    "gitBaseline": {
                        "revision": bootstrap.revision,
                        "modified": bootstrap.modified_count,
                        "untracked": bootstrap.untracked_count,
                    },
                    "toolchain": {
                        "kind": bootstrap.toolchain_kind,
                        "testFrameworks": list(bootstrap.test_frameworks),
                    },
                },
            }

    def _ensure_project_context_ready(self, session: Session, project_id: str) -> None:
        project = session.get(Project, project_id)
        if project is None:
            raise HarnessError("PROJECT_NOT_FOUND", "project not found")
        revision = GitService(project.root_path).base_revision()
        key = f"project-understanding:{revision[:12]}"
        from se_mentor.models.knowledge import EngineeringKnowledge

        exists = session.scalar(
            select(EngineeringKnowledge.id)
            .where(EngineeringKnowledge.project_id == project_id)
            .where(EngineeringKnowledge.knowledge_key == key)
        )
        if exists is None:
            raise HarnessError(
                "CONTEXT_BUILD_FAILED",
                "Project analysis is not ready; proposal context is not available yet.",
            )

    def _resolved_project_path(self, project_path: str | Path) -> str:
        settings = get_runtime_settings()
        if settings.profile is not RuntimeProfile.CLOUD_DEMO:
            return str(Path(project_path).expanduser())
        demo_root = ensure_demo_workspace(settings.demo_workspace_root)
        requested_root = Path(project_path).expanduser().resolve(strict=True)
        if requested_root != demo_root:
            raise HarnessError(
                "CLOUD_DEMO_PROJECT_RESTRICTED",
                "demo mode only allows the predefined demo workspace",
            )
        return str(demo_root)


def _task_summary(task: ChangeTask) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        project_id=task.project_id,
        request=task.original_request,
        status=str(task.status),
    )


def _proposal_summary(proposal: ChangeProposal) -> ProposalSummary:
    constraints = _json_object(proposal.constraints_json)
    risks = _json_object(proposal.risks_json)
    current_problem = _json_object(proposal.current_problem)
    return ProposalSummary(
        id=proposal.id,
        task_id=proposal.task_id,
        version=proposal.version,
        goal=proposal.goal,
        understanding=str(current_problem.get("understanding") or proposal.goal),
        expected_behavior=proposal.expected_behavior,
        scope=tuple(_json_list(proposal.initial_scope_json)),
        changes=tuple(_json_dicts(constraints.get("changes"))),
        steps=tuple(_json_strings(constraints.get("steps"))),
        risks=tuple(_json_strings(risks.get("risks"))),
        acceptance=tuple(_json_list(proposal.acceptance_criteria_json)),
        validation=tuple(_json_list(proposal.validation_plan_json)),
        completeness=str(proposal.completeness),
        status=str(proposal.status),
    )


def _impact_summary(report: ImpactReport) -> ImpactSummary:
    return ImpactSummary(
        id=report.id,
        direct_count=len(_json_items(report.direct_impacts_json)),
        indirect_count=len(_json_items(report.indirect_impacts_json)),
        unknown_count=len(_json_items(report.uncertainties_json)),
    )


def _governance_summary(decision: GovernanceDecision) -> GovernanceSummary:
    return GovernanceSummary(
        id=decision.id,
        decision=str(decision.decision),
        reason=decision.reason_summary,
        approval_required=bool(decision.approval_required),
        allowed_scope=tuple(_json_list(decision.allowed_scope_json)),
        denied_scope=tuple(_json_list(decision.denied_scope_json)),
        rule_hits=tuple(
            {
                "effect": hit.effect,
                "ruleId": hit.rule_id,
                "evidence": _json_items(hit.matched_evidence_json),
            }
            for hit in decision.rule_hits
        ),
    )


def _proposal_message_text(proposal: ChangeProposal) -> str:
    if proposal.completeness == ProposalCompleteness.COMPLETE:
        return f"Proposal v{proposal.version} is ready for review."
    if proposal.completeness == ProposalCompleteness.PARTIALLY_COMPLETE:
        return f"Proposal v{proposal.version} needs a user decision before confirmation."
    return f"Proposal v{proposal.version} still needs technical analysis before confirmation."


def _add_workbench_message(
    session: Session,
    *,
    task_id: str,
    role: str,
    kind: str,
    status: str,
    text: str,
    proposal_id: str | None = None,
) -> None:
    sequence = (
        int(
            session.scalar(
                select(func.coalesce(func.max(WorkbenchMessage.sequence), 0)).where(
                    WorkbenchMessage.task_id == task_id
                )
            )
            or 0
        )
        + 1
    )
    session.add(
        WorkbenchMessage(
            task_id=task_id,
            sequence=sequence,
            role=role,
            kind=kind,
            status=status,
            text=workbench_message_text(role=role, kind=kind, text=text),
            proposal_id=proposal_id,
        )
    )


def _quick_revision(root_path: str) -> str | None:
    try:
        return GitService(root_path).base_revision()
    except Exception:
        return None


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    data = json.loads(value)
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    data = json.loads(value)
    if isinstance(data, dict):
        return data
    return {}


def _json_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _json_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_items(value: str | None) -> list[object]:
    if not value:
        return []
    data = json.loads(value)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return [data] if data else []
