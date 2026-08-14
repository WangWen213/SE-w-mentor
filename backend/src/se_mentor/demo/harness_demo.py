from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from se_mentor.agent.iteration import SingleTurnAgentRunner
from se_mentor.context.context_builder import ContextBuilder, ContextItem, TrustLabel
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine, session_scope
from se_mentor.feedback.controller import FeedbackController, FeedbackSource
from se_mentor.governance.rule_repository import RuleDefinition
from se_mentor.knowledge.repository import KnowledgeRepository
from se_mentor.knowledge.retrieval import KnowledgeHit, KnowledgeRetriever
from se_mentor.llm.base import LLMRequest, LLMResponse
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.governance import (
    GovernanceDecision,
    GovernanceRuleEffect,
    GovernanceRuleScope,
)
from se_mentor.models.knowledge import EngineeringKnowledge, KnowledgeStatus, KnowledgeType
from se_mentor.models.llm import AgentAction
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskIteration,
    TaskIterationPhase,
    TaskStatus,
)
from se_mentor.models.validation import FeedbackSignal
from se_mentor.tools.registry import ToolRegistry, ToolSpec

PROPOSAL_HASH = "d" * 64
REVISION = "deterministic-demo-revision"
SCENARIO_ORDER = ("governance", "feedback", "memory")
SCENARIO_TITLES = {
    "governance": "Governance Guardrail",
    "feedback": "Feedback-driven Self Correction",
    "memory": "Engineering Memory / Context",
}


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    title: str
    passed: bool
    evidence: dict[str, object]
    error: str | None = None


@dataclass(frozen=True)
class DemoRunResult:
    passed: bool
    results: tuple[ScenarioResult, ...]
    output_dir: str | None


class CapturingMockLLMProvider(MockLLMProvider):
    def __init__(self, *, model: str, script: tuple[MockResponse, ...]) -> None:
        super().__init__(model=model, script=script)
        self.requests: list[str] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request.input_text)
        return super().complete(request)


class DemoAssertionError(AssertionError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(f"{stage}: expected {expected}; actual {actual}")
        self.stage = stage
        self.expected = expected
        self.actual = actual


def run_demo(
    *,
    scenario: str | None = None,
    all_scenarios: bool = False,
    output: str | Path | None = None,
    verbose: bool = False,
) -> DemoRunResult:
    selected = _selected_scenarios(scenario=scenario, all_scenarios=all_scenarios)
    output_dir = Path(output).resolve() if output is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    results: list[ScenarioResult] = []
    for scenario_name in selected:
        try:
            result = _SCENARIOS[scenario_name](verbose=verbose)
        except DemoAssertionError as exc:
            result = ScenarioResult(
                scenario=scenario_name,
                title=SCENARIO_TITLES[scenario_name],
                passed=False,
                evidence={"stage": exc.stage, "expected": exc.expected, "actual": exc.actual},
                error=str(exc),
            )
        except Exception as exc:
            result = ScenarioResult(
                scenario=scenario_name,
                title=SCENARIO_TITLES[scenario_name],
                passed=False,
                evidence={
                    "stage": "runtime",
                    "expected": "no exception",
                    "actual": type(exc).__name__,
                },
                error=str(exc),
            )
        results.append(result)

    run_result = DemoRunResult(
        passed=all(result.passed for result in results),
        results=tuple(results),
        output_dir=str(output_dir) if output_dir is not None else None,
    )
    if output_dir is not None:
        _write_evidence(output_dir, run_result)
    return run_result


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        run_result = run_demo(
            scenario=args.scenario,
            all_scenarios=args.all,
            output=args.output,
            verbose=args.verbose,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _print_result(run_result, verbose=args.verbose)
    return 0 if run_result.passed else 1


def _selected_scenarios(*, scenario: str | None, all_scenarios: bool) -> tuple[str, ...]:
    if all_scenarios:
        if scenario is not None:
            raise ValueError("--all cannot be combined with --scenario")
        return SCENARIO_ORDER
    if scenario is None:
        raise ValueError("choose --all or --scenario")
    return (scenario,)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic offline SE-Mentor harness mechanism demo."
    )
    parser.add_argument("--all", action="store_true", help="run all demo scenarios")
    parser.add_argument(
        "--scenario",
        choices=SCENARIO_ORDER,
        help="run one scenario: governance, feedback, or memory",
    )
    parser.add_argument("--output", help="write JSON evidence files to this directory")
    parser.add_argument("--verbose", action="store_true", help="print compact scenario evidence")
    return parser


def _run_governance(*, verbose: bool) -> ScenarioResult:
    with _demo_runtime() as runtime:
        provider = CapturingMockLLMProvider(
            model="mock-mechanism-demo",
            script=(
                MockResponse(
                    match="dangerous cleanup",
                    content=(
                        '{"action_type":"DELETE_FILE",'
                        '"parameters":{"path":"secrets.env"},'
                        '"reason":"remove obsolete local credentials"}'
                    ),
                    input_tokens=31,
                    output_tokens=19,
                ),
            ),
        )
        rules = (
            RuleDefinition(
                key="protect-credential-fixture",
                name="Protect credential-like files",
                scope=GovernanceRuleScope.SYSTEM,
                effect=GovernanceRuleEffect.DENY_HARD,
                priority=100,
                patterns=("secrets.env",),
                conditions={"path": True},
                reason="Credential-like files cannot be deleted or modified.",
                overridable=False,
            ),
        )

        with session_scope(runtime.session_factory) as session:
            runner = SingleTurnAgentRunner(
                session,
                project_root=runtime.repo,
                context_builder=ContextBuilder(max_chars=4000),
                provider=provider,
                registry=_registry("DELETE_FILE"),
                tool_handlers={"DELETE_FILE": lambda action: _delete(runtime.repo, action)},
                governance_rules=rules,
            )
            result = runner.run(
                task_id=runtime.ids["task_id"],
                proposal_hash=PROPOSAL_HASH,
                revision=REVISION,
                goal="dangerous cleanup",
            )
            action = session.get(AgentAction, result.action_id)
            decision = _latest(session, GovernanceDecision)

        dangerous_executed = not (runtime.repo / "secrets.env").exists()
        _assert_equal("governance_decision", "BLOCK", str(decision.decision))
        _assert_equal("dangerous_tool_executed", "false", str(dangerous_executed).lower())
        evidence = {
            "requested_action": action.parameters_summary if action is not None else None,
            "action_type": action.action_type if action is not None else None,
            "governance_decision": str(decision.decision),
            "matched_rule": "protect-credential-fixture",
            "reason": decision.reason_summary,
            "dispatcher_invoked": result.tool_result is not None,
            "tool_executed": dangerous_executed,
            "final_state": "BLOCKED",
            "provider": provider.provider_name,
            "provider_calls": provider.calls,
        }
        return ScenarioResult("governance", SCENARIO_TITLES["governance"], True, evidence)


def _run_feedback(*, verbose: bool) -> ScenarioResult:
    with _demo_runtime() as runtime:
        provider = CapturingMockLLMProvider(
            model="mock-mechanism-demo",
            script=(
                MockResponse(
                    match="initial contract attempt",
                    content=(
                        '{"action_type":"APPLY_PATCH",'
                        '"parameters":{"relative_path":"app.py","expected_sha256":null,'
                        '"replacements":[{"old":"return 1","new":"return 2"}]},'
                        '"reason":"first attempted fix"}'
                    ),
                    input_tokens=41,
                    output_tokens=29,
                    min_call=1,
                ),
                MockResponse(
                    match="CONTRACT_FAILURE",
                    content=(
                        '{"action_type":"APPLY_PATCH",'
                        '"parameters":{"relative_path":"app.py","expected_sha256":null,'
                        '"replacements":[{"old":"return 2","new":"return 42"}]},'
                        '"reason":"respond to validation feedback"}'
                    ),
                    input_tokens=53,
                    output_tokens=31,
                    min_call=2,
                ),
            ),
        )
        with session_scope(runtime.session_factory) as session:
            runner = SingleTurnAgentRunner(
                session,
                project_root=runtime.repo,
                context_builder=ContextBuilder(max_chars=4000),
                provider=provider,
                registry=_registry("APPLY_PATCH"),
                tool_handlers={"APPLY_PATCH": _patch_handler(runtime.repo)},
            )
            first = runner.run(
                task_id=runtime.ids["task_id"],
                proposal_hash=PROPOSAL_HASH,
                revision=REVISION,
                goal="initial contract attempt",
            )
            first_action = session.get(AgentAction, first.action_id)
            first_validation = _validate_answer(runtime.repo)
            feedback = FeedbackController(session).create(
                task_id=runtime.ids["task_id"],
                source=FeedbackSource(
                    source_type="validation",
                    category="CONTRACT_FAILURE",
                    retryable=True,
                    log_text=(
                        "FAILED tests/test_app.py::test_answer\n"
                        "AssertionError: expected answer() == 42"
                    ),
                    artifact_ref=str(runtime.root / "validation.log"),
                ),
            )
            second = runner.run(
                task_id=runtime.ids["task_id"],
                proposal_hash=PROPOSAL_HASH,
                revision=REVISION,
                goal="apply validation repair",
                feedback=feedback.message,
            )
            second_action = session.get(AgentAction, second.action_id)
            second_validation = _validate_answer(runtime.repo)
            stored_feedback = session.query(FeedbackSignal).one()

        first_summary = first_action.parameters_summary if first_action is not None else ""
        second_summary = second_action.parameters_summary if second_action is not None else ""
        feedback_in_context = any(
            "CONTRACT_FAILURE" in request for request in provider.requests[1:]
        )
        _assert_equal("first_validation", "FAIL", "PASS" if first_validation else "FAIL")
        _assert_equal("feedback_in_next_context", "true", str(feedback_in_context).lower())
        _assert_equal("action_changed", "true", str(first_summary != second_summary).lower())
        _assert_equal("second_validation", "PASS", "PASS" if second_validation else "FAIL")
        evidence = {
            "demo_task": "fix failing contract",
            "first_action": first_summary,
            "first_validation": "FAIL",
            "feedback_generated": True,
            "feedback_in_next_provider_context": feedback_in_context,
            "second_action": second_summary,
            "action_changed": first_summary != second_summary,
            "second_validation": "PASS",
            "final_state": "answer() returns 42",
            "feedback_signal_id": stored_feedback.id,
            "provider": provider.provider_name,
            "provider_calls": provider.calls,
        }
        return ScenarioResult("feedback", SCENARIO_TITLES["feedback"], True, evidence)


def _run_memory(*, verbose: bool) -> ScenarioResult:
    with _demo_runtime() as runtime:
        with session_scope(runtime.session_factory) as session:
            knowledge = KnowledgeRepository(session).add(
                project_id=runtime.ids["project_id"],
                key="answer-contract",
                knowledge_type=KnowledgeType.PATTERN,
                status=KnowledgeStatus.VERIFIED,
                scope_paths=("app.py",),
                summary="For app.py, answer() must return 42 to satisfy the product contract.",
                evidence_refs=("evidence://deterministic-demo/memory",),
            )
            hits = KnowledgeRetriever(session).search(
                project_id=runtime.ids["project_id"],
                paths=("app.py",),
                keywords=("answer", "42"),
            )
            package = ContextBuilder(max_chars=4000).build(
                goal="new task: update app.py using remembered answer contract",
                governance_items=(
                    ContextItem(
                        "governance",
                        "governance",
                        "governance required",
                        100,
                        TrustLabel.SYSTEM,
                    ),
                ),
                execution_policy=ContextItem(
                    "policy",
                    "policy",
                    "write scope: app.py",
                    95,
                    TrustLabel.SYSTEM,
                ),
                current_error=ContextItem(
                    "feedback", "feedback", "none", 90, TrustLabel.TOOL_OUTPUT
                ),
                repository_items=(),
                knowledge_items=_knowledge_context_items(session, hits),
            )

        provider = CapturingMockLLMProvider(
            model="mock-mechanism-demo",
            script=(
                MockResponse(
                    match="answer() must return 42",
                    content=(
                        '{"action_type":"APPLY_PATCH",'
                        '"parameters":{"relative_path":"app.py","expected_sha256":null,'
                        '"replacements":[{"old":"return 1","new":"return 42"}]},'
                        '"reason":"use retrieved engineering memory"}'
                    ),
                    input_tokens=37,
                    output_tokens=25,
                ),
            ),
        )
        response = provider.complete(
            LLMRequest(prompt_summary="memory scenario", input_text=package.render())
        )
        parsed = json.loads(response.content)
        context_render = package.render()
        retrieval_hit = len(hits) > 0 and hits[0].knowledge_key == "answer-contract"
        context_injected = "answer() must return 42" in context_render
        behavior_affected = "return 42" in response.content
        _assert_equal("knowledge_persisted", "true", str(bool(knowledge.id)).lower())
        _assert_equal("retrieval", "HIT", "HIT" if retrieval_hit else "MISS")
        _assert_equal("context_injected", "true", str(context_injected).lower())
        _assert_equal("agent_behavior_affected", "true", str(behavior_affected).lower())
        evidence = {
            "stored_engineering_knowledge": knowledge.knowledge_key,
            "persistence_path": "engineering_knowledge",
            "new_task_context": True,
            "retrieval_path": "KnowledgeRetriever.search",
            "retrieval_result": "HIT",
            "context_injection_path": "ContextBuilder.build(knowledge_items=...)",
            "provider_received_memory": context_injected,
            "resulting_action": parsed,
            "behavior_affected": behavior_affected,
            "provider": provider.provider_name,
            "provider_calls": provider.calls,
        }
        return ScenarioResult("memory", SCENARIO_TITLES["memory"], True, evidence)


@dataclass(frozen=True)
class _Runtime:
    root: Path
    repo: Path
    engine: Engine
    session_factory: Any
    ids: dict[str, str]

    def __enter__(self) -> _Runtime:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.engine.dispose()
        shutil.rmtree(self.root, ignore_errors=True)


def _demo_runtime() -> _Runtime:
    root = Path(tempfile.mkdtemp(prefix="sementor-mechanism-demo-"))
    repo = root / "fixture-repo"
    repo.mkdir()
    (repo / "app.py").write_text("def answer():\n    return 1\n", encoding="utf-8")
    (repo / "secrets.env").write_text("DEMO_ONLY=placeholder\n", encoding="utf-8")
    _init_git(repo)
    engine = create_sqlite_engine(f"sqlite:///{root / 'demo.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    ids = _seed_task_graph(session_factory, repo)
    return _Runtime(root, repo, engine, session_factory, ids)


def _init_git(repo: Path) -> None:
    commands = (
        ("git", "init"),
        ("git", "config", "user.email", "demo@example.invalid"),
        ("git", "config", "user.name", "SE Mentor Demo"),
        ("git", "add", "."),
        ("git", "commit", "-m", "initial fixture"),
    )
    for command in commands:
        subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)


def _seed_task_graph(session_factory: Any, repo: Path) -> dict[str, str]:
    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        task = ChangeTask(
            project_id=project.id,
            original_request="Deterministic mechanism demo task.",
            base_revision=REVISION,
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        proposal = ChangeProposal(
            task_id=task.id,
            version=1,
            goal="Deterministic mechanism demo.",
            expected_behavior="Harness mechanisms remain observable.",
            initial_scope_json='["app.py"]',
            acceptance_criteria_json='["demo evidence passes"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.CONFIRMED,
            created_by_type=ProposalCreatedByType.SYSTEM,
        )
        session.add(proposal)
        session.flush()
        iteration = TaskIteration(
            task_id=task.id,
            iteration_number=1,
            phase=TaskIterationPhase.ANALYZE,
        )
        session.add(iteration)
        session.flush()
        return {"project_id": project.id, "task_id": task.id, "proposal_id": proposal.id}


def _registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(ToolSpec(name, "demo", 10))
    return registry


def _delete(repo: Path, action: Any) -> str:
    (repo / action.parameters.path).unlink()
    return "deleted"


def _patch_handler(repo: Path) -> Callable[[Any], str]:
    def handler(action: Any) -> str:
        target = repo / action.parameters.relative_path
        text = target.read_text(encoding="utf-8")
        for replacement in action.parameters.replacements:
            text = text.replace(replacement.old, replacement.new)
        target.write_text(text, encoding="utf-8")
        return "patched"

    return handler


def _validate_answer(repo: Path) -> bool:
    namespace: dict[str, object] = {}
    exec((repo / "app.py").read_text(encoding="utf-8"), namespace)
    answer = namespace.get("answer")
    return callable(answer) and answer() == 42


def _knowledge_context_items(
    session: Any, hits: tuple[KnowledgeHit, ...]
) -> tuple[ContextItem, ...]:
    items: list[ContextItem] = []
    for hit in hits:
        row = session.get(EngineeringKnowledge, hit.knowledge_id)
        if row is None:
            continue
        items.append(
            ContextItem(
                item_id=f"knowledge:{row.knowledge_key}",
                section="knowledge",
                text=row.summary,
                priority=hit.score,
                trust_label=TrustLabel.SYSTEM,
            )
        )
    return tuple(items)


def _latest(session: Any, model: Any) -> Any:
    return session.query(model).order_by(model.created_at.desc(), model.id.desc()).first()


def _assert_equal(stage: str, expected: str, actual: str) -> None:
    if expected != actual:
        raise DemoAssertionError(stage, expected, actual)


def _write_evidence(output_dir: Path, result: DemoRunResult) -> None:
    (output_dir / "summary.json").write_text(
        json.dumps(_result_payload(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    for scenario_result in result.results:
        (output_dir / f"{scenario_result.scenario}.json").write_text(
            json.dumps(_scenario_payload(scenario_result), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _result_payload(result: DemoRunResult) -> dict[str, object]:
    return {
        "passed": result.passed,
        "scenarios_passed": sum(1 for item in result.results if item.passed),
        "scenarios_total": len(result.results),
        "results": [_scenario_payload(item) for item in result.results],
        "offline": True,
        "mock_provider_only": True,
        "network_calls": 0,
        "real_api_key_required": False,
        "credential_manager_accessed": False,
    }


def _scenario_payload(result: ScenarioResult) -> dict[str, object]:
    return {
        "scenario": result.scenario,
        "title": result.title,
        "passed": result.passed,
        "evidence": result.evidence,
        "error": result.error,
    }


def _print_result(result: DemoRunResult, *, verbose: bool) -> None:
    for item in result.results:
        print(f"[{SCENARIO_ORDER.index(item.scenario) + 1}/3] {item.title}")
        if item.scenario == "governance":
            print(f"Governance decision: {item.evidence.get('governance_decision')}")
            print(
                f"Dangerous tool executed: {'YES' if item.evidence.get('tool_executed') else 'NO'}"
            )
        if item.scenario == "feedback":
            print(f"Attempt 1 validation: {item.evidence.get('first_validation')}")
            print(
                "Feedback returned to agent: "
                f"{'YES' if item.evidence.get('feedback_in_next_provider_context') else 'NO'}"
            )
            print(f"Action changed: {'YES' if item.evidence.get('action_changed') else 'NO'}")
            print(f"Attempt 2 validation: {item.evidence.get('second_validation')}")
        if item.scenario == "memory":
            print(
                "Knowledge persisted: "
                f"{'YES' if item.evidence.get('stored_engineering_knowledge') else 'NO'}"
            )
            print(f"Retrieval: {item.evidence.get('retrieval_result')}")
            print(
                "Context injected: "
                f"{'YES' if item.evidence.get('provider_received_memory') else 'NO'}"
            )
            print(
                "Agent behavior affected: "
                f"{'YES' if item.evidence.get('behavior_affected') else 'NO'}"
            )
        if verbose:
            print(json.dumps(item.evidence, indent=2, sort_keys=True, default=str))
        if not item.passed:
            print("RESULT: FAIL")
            print(f"Scenario: {item.title}")
            print(f"Stage: {item.evidence.get('stage')}")
            print(f"Expected: {item.evidence.get('expected')}")
            print(f"Actual: {item.evidence.get('actual')}")
            if item.error:
                print(f"Error: {item.error}")
        else:
            print("RESULT: PASS")
        print()
    passed = sum(1 for item in result.results if item.passed)
    print(f"Scenarios passed: {passed} / {len(result.results)}")


_SCENARIOS: dict[str, Callable[..., ScenarioResult]] = {
    "governance": _run_governance,
    "feedback": _run_feedback,
    "memory": _run_memory,
}


if __name__ == "__main__":
    raise SystemExit(main())
