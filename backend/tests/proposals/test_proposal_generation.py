from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, seed_task_graph

from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.llm.base import LLMRequest
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.models.task import ChangeProposal
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
                content=(
                    '{"goal":"Add audit logs","expected_behavior":"Audit logs are persisted",'
                    '"scope":["backend/src"],"non_goals":["frontend"],'
                    '"constraints":["no network"],"acceptance":["pytest passes"],'
                    '"user_facts":["User asked for audit logs"],'
                    '"inferences":["Backend service likely changes"],"risks":["schema drift"]}'
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
