from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.api.proposals import _run_bounded_technical_supplement
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.base import LLMRequest
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalStatus,
    TaskStatus,
)
from se_mentor.proposals import context as proposal_context
from se_mentor.proposals.context import ProposalContextBuilder
from se_mentor.proposals.generator import ProposalGenerationError, ProposalGenerator


def test_AC_FR02_01_generates_required_proposal_fields_without_side_effects(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "proposal.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    before = sorted(path.name for path in repo.iterdir())
    provider = MockLLMProvider(
        model="mock",
        script=(
            MockResponse(
                match="proposal",
                content=json.dumps(
                    {
                        "goal": "Add audit logs",
                        "understanding": "User wants persisted audit logs",
                        "expected_behavior": "Audit logs are persisted",
                        "scope": ["backend/src"],
                        "changes": [
                            {
                                "path": "backend/src",
                                "symbol": None,
                                "action": "Add audit log persistence",
                                "reason": "Repository backend scope is evidenced",
                            }
                        ],
                        "steps": ["Locate audit model", "Persist audit event"],
                        "non_goals": ["frontend"],
                        "constraints": ["no network"],
                        "acceptance": ["pytest passes"],
                        "validation": ["pytest passes"],
                        "user_facts": ["User asked for audit logs"],
                        "inferences": ["Backend service likely changes"],
                        "risks": ["schema drift"],
                    }
                ),
                input_tokens=11,
                output_tokens=17,
            ),
        ),
    )

    with session_scope(session_factory) as session:
        generator = ProposalGenerator(session, provider)
        proposal = generator.generate(
            task_id=ids["task_id"],
            request=LLMRequest(prompt_summary="proposal", input_text="proposal: add audit logs"),
        )
        proposal_id = proposal.id

    assert sorted(path.name for path in repo.iterdir()) == before
    with session_scope(session_factory) as session:
        stored = session.get(ChangeProposal, proposal_id)
        assert stored is not None
        assert stored.version == 2
        assert stored.goal == "Add audit logs"
        assert stored.assumptions_json is not None
        assert stored.risks_json is not None
        assert "User asked" in stored.assumptions_json
        assert "Backend service likely changes" in stored.risks_json

    with session_scope(session_factory) as session:
        bad = ProposalGenerator(
            session,
            MockLLMProvider(
                model="mock",
                script=(
                    MockResponse(
                        match="bad",
                        content='{"goal":"x","unknown":true}',
                        input_tokens=1,
                        output_tokens=1,
                    ),
                ),
            ),
        )
        with pytest.raises(ProposalGenerationError):
            bad.generate(
                task_id=ids["task_id"],
                request=LLMRequest(prompt_summary="bad", input_text="bad"),
            )


def test_bounded_technical_supplement_runs_once_and_reaches_terminal_state(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "proposal-supplement.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "frontend").mkdir()
    (repo / "frontend" / "nav.ts").write_text("export const label = '任务';\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    provider = MockLLMProvider(
        model="mock",
        script=(
            MockResponse(
                match="Bounded technical supplement",
                content=json.dumps(
                    {
                        "goal": "Update sidebar task label",
                        "understanding": "User wants a sidebar label text change",
                        "expected_behavior": "The sidebar shows the updated task label",
                        "scope": ["frontend/src/app/fixtures.ts"],
                        "changes": [
                            {
                                "path": "frontend/src/app/fixtures.ts",
                                "symbol": None,
                                "action": "Update label text",
                                "reason": "Navigation labels live in fixtures",
                            }
                        ],
                        "steps": ["Locate navigation item", "Update label text"],
                        "non_goals": ["No layout changes"],
                        "constraints": ["Keep existing navigation behavior"],
                        "acceptance": ["Sidebar label is updated"],
                        "validation": ["Run frontend type-check"],
                        "user_facts": ["User requested a text-only sidebar label change"],
                        "inferences": ["Navigation label is frontend-only"],
                        "risks": ["Localization text drift"],
                    }
                ),
                input_tokens=10,
                output_tokens=10,
            ),
        ),
    )

    with session_scope(session_factory) as session:
        task = session.get(ChangeTask, ids["task_id"])
        assert task is not None
        incomplete = ChangeProposal(
            task_id=ids["task_id"],
            version=2,
            goal="Update sidebar task label",
            current_problem='{"understanding":"Update sidebar task label"}',
            expected_behavior="Sidebar label changes",
            initial_scope_json='["UNKNOWN"]',
            acceptance_criteria_json='["Updated label is visible"]',
            validation_plan_json='["Run frontend type-check"]',
            constraints_json=json.dumps(
                {
                    "changes": [
                        {
                            "path": "UNKNOWN",
                            "symbol": None,
                            "action": "TBD",
                            "reason": "Need technical localization",
                        }
                    ],
                    "steps": ["TBD"],
                    "constraints": [],
                }
            ),
            risks_json='{"risks":["UNKNOWN"],"inferences":[]}',
            assumptions_json="{}",
            completeness=ProposalCompleteness.INCOMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type="LLM",
        )
        session.add(incomplete)
        session.flush()
        task.failure_message = "technical unknowns: scope UNKNOWN"
        context = ProposalContextBuilder(session).build_for_task(
            ids["task_id"], "Update sidebar task label"
        )

        supplemented = _run_bounded_technical_supplement(
            session,
            ProposalGenerator(session, provider),
            task,
            incomplete,
            context,
        )

        assert provider.calls == 1
        assert incomplete.status == ProposalStatus.SUPERSEDED
        assert supplemented.supersedes_id == incomplete.id
        assert supplemented.completeness == ProposalCompleteness.COMPLETE
        assert task.status == TaskStatus.PROPOSAL_REVIEW


def test_tracked_paths_cache_reuses_git_index_for_same_revision(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    calls = 0

    class Result:
        stdout = b"README.md\0"

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Result()

    proposal_context._TRACKED_PATH_CACHE.clear()
    monkeypatch.setattr(proposal_context.subprocess, "run", fake_run)

    first = proposal_context._git_index_paths(repo, project_id="project-1", revision="rev-1")
    second = proposal_context._git_index_paths(repo, project_id="project-1", revision="rev-1")
    third = proposal_context._git_index_paths(repo, project_id="project-1", revision="rev-2")

    assert first == ("README.md",)
    assert second == first
    assert third == first
    assert calls == 2
