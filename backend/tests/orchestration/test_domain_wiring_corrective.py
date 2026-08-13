from __future__ import annotations

import json
import subprocess
from pathlib import Path

from phase1_test_helpers import create_schema

from se_mentor.api.runtime import build_openai_provider
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.indexing.python_indexer import PythonIndexer
from se_mentor.indexing.relation_extractor import RelationExtractor
from se_mentor.llm.base import LLMRequest, LLMResponse, LLMUsage
from se_mentor.models.governance import GovernanceDecision, ImpactReport
from se_mentor.models.project import Project
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
    TaskStatus,
)
from se_mentor.orchestration.change_flow import ChangeFlowOrchestrator
from se_mentor.projects.bootstrap import ProjectBootstrapService
from se_mentor.proposals.context import ProposalContextBuilder
from se_mentor.proposals.generator import ProposalGenerator
from se_mentor.security.secrets import Secret


class RecordingProvider:
    provider_name = "recording"
    model = "recording"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if "impact" in request.prompt_summary.lower():
            data = json.loads(request.input_text)
            return LLMResponse(
                content=json.dumps(
                    {
                        "narrative": "Impact is grounded in repository evidence.",
                        "fact_refs": data["evidence_ids"],
                        "risks": data["unknowns"],
                    },
                    sort_keys=True,
                ),
                usage=LLMUsage(10, 10),
                model=self.model,
                provider=self.provider_name,
            )
        return LLMResponse(
            content=json.dumps(
                {
                    "goal": "Update the real README behavior",
                    "understanding": (
                        "User wants the README updated using the real repository path."
                    ),
                    "expected_behavior": (
                        "README describes the requested behavior for this repository."
                    ),
                    "scope": ["README.md"],
                    "changes": [
                        {
                            "path": "README.md",
                            "symbol": None,
                            "action": "Update README content for the requested behavior.",
                            "reason": "README.md exists in the indexed repository.",
                        }
                    ],
                    "steps": ["Read README.md", "Apply the requested documentation change"],
                    "non_goals": ["No unrelated files are changed."],
                    "constraints": ["Use evidenced paths from context."],
                    "acceptance": ["README.md is reviewed after the change."],
                    "validation": ["README.md is reviewed after the change."],
                    "user_facts": ["User asked to update README."],
                    "inferences": ["README.md exists in the indexed repository."],
                    "risks": ["No code behavior is changed."],
                },
                sort_keys=True,
            ),
            usage=LLMUsage(10, 20),
            model=self.model,
            provider=self.provider_name,
        )


def test_configured_provider_selects_openai_provider_without_template() -> None:
    provider = build_openai_provider(Secret("sk-test"))

    assert provider.provider_name == "openai"
    assert provider.__class__.__name__ == "OpenAIResponsesProvider"


def test_project_bootstrap_and_proposal_use_repository_context(tmp_path: Path, monkeypatch) -> None:
    repo = _git_repo(tmp_path)
    engine = create_schema(tmp_path / "wiring.sqlite3")
    session_factory = create_session_factory(engine)
    provider = RecordingProvider()

    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        bootstrap = ProjectBootstrapService(session).bootstrap(project.id)
        task = ChangeTask(
            project_id=project.id,
            original_request="Update README",
            base_revision=bootstrap.revision,
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()

        def fail_walk(*_args, **_kwargs):
            raise AssertionError("proposal context must use indexed paths, not repository walks")

        monkeypatch.setattr("se_mentor.proposals.context.os.walk", fail_walk)
        context = ProposalContextBuilder(session).build_for_task(task.id, "Update README")
        proposal = ProposalGenerator(session, provider).generate(
            task_id=task.id,
            request=LLMRequest(
                prompt_summary="structured change proposal",
                input_text="Update README",
            ),
            context_package=context.context_package,
            evidenced_paths=context.evidenced_paths,
        )

        assert bootstrap.file_count >= 1
        assert bootstrap.symbol_count >= 1
        assert "README.md" in context.evidenced_paths
        assert "file:README.md" in provider.requests[0].input_text
        assert json.loads(proposal.initial_scope_json) == ["README.md"]


def test_confirm_triggers_impact_and_governance(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    engine = create_schema(tmp_path / "confirm.sqlite3")
    session_factory = create_session_factory(engine)
    provider = RecordingProvider()

    with session_scope(session_factory) as session:
        project = Project(root_path=str(repo))
        session.add(project)
        session.flush()
        revision = ProjectBootstrapService(session).bootstrap(project.id).revision
        PythonIndexer(session).build(project.id, repo, revision)
        RelationExtractor(session).extract(project.id, repo, revision)
        task = ChangeTask(
            project_id=project.id,
            original_request="Update README",
            base_revision=revision,
            status=TaskStatus.CREATED,
        )
        session.add(task)
        session.flush()
        proposal = ChangeProposal(
            task_id=task.id,
            version=1,
            goal="Update README",
            expected_behavior="README is updated.",
            initial_scope_json='["README.md"]',
            acceptance_criteria_json='["README reviewed"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        session.add(proposal)
        session.flush()
        result = ChangeFlowOrchestrator(session, provider).confirm_and_analyze(
            proposal.id,
            actor_id="test-user",
        )

        assert result.proposal.status == ProposalStatus.CONFIRMED
        assert session.query(ImpactReport).count() == 1
        assert session.query(GovernanceDecision).count() == 1
        assert result.governance_decision.impact_report_id == result.impact_report.id
        assert task.status == TaskStatus.ACTION_PENDING


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    (repo / "app.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo
