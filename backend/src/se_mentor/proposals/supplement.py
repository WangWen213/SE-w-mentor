from __future__ import annotations

from sqlalchemy.orm import Session

from se_mentor.llm.base import LLMRequest
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalStatus,
    TaskStatus,
)
from se_mentor.proposals.generator import ProposalGenerator


def run_bounded_technical_supplement(
    session: Session,
    generator: ProposalGenerator,
    task: ChangeTask,
    proposal: ChangeProposal,
    context,
) -> ChangeProposal:
    reason = task.failure_message or "Proposal needs one bounded technical supplement."
    supplemented = generator.generate(
        task_id=task.id,
        request=LLMRequest(
            prompt_summary="structured technical proposal supplement",
            input_text="\n".join(
                [
                    "Bounded technical supplement for the existing proposal.",
                    f"Original request: {task.original_request}",
                    f"Current proposal version: {proposal.version}",
                    f"Missing technical analysis: {reason}",
                    "Reuse the existing selected context and fill only missing technical details.",
                ]
            ),
        ),
        context_package=context.context_package,
        evidenced_paths=context.evidenced_paths,
    )
    proposal.status = ProposalStatus.SUPERSEDED
    supplemented.supersedes_id = proposal.id
    if supplemented.completeness == ProposalCompleteness.COMPLETE:
        task.failure_code = None
        task.failure_message = None
    elif supplemented.completeness == ProposalCompleteness.PARTIALLY_COMPLETE:
        task.status = TaskStatus.NEEDS_INFORMATION
    else:
        task.status = TaskStatus.FAILED
        task.failure_code = "PROPOSAL_INCOMPLETE_AFTER_SUPPLEMENT"
        task.failure_message = (
            "Proposal technical supplement completed but did not produce a confirmable proposal."
        )
    session.flush()
    return supplemented

