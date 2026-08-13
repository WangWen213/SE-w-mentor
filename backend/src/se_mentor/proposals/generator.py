from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from se_mentor.context.context_builder import ContextPackage
from se_mentor.llm.base import LLMProvider, LLMRequest
from se_mentor.models.task import (
    ChangeProposal,
    ChangeTask,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
)
from se_mentor.proposals.completeness import ProposalCompletenessService

LOGGER = logging.getLogger("se_mentor.proposals.generator")


class ProposalGenerationError(ValueError):
    code = "PROPOSAL_GENERATION_FAILED"

    def __init__(
        self,
        message: str,
        *,
        actual_keys: list[str] | None = None,
        expected_keys: list[str] | None = None,
        validation_errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.actual_keys = actual_keys or []
        self.expected_keys = expected_keys or []
        self.validation_errors = validation_errors or []


class ProposalResponseEmpty(ProposalGenerationError):
    code = "PROPOSAL_RESPONSE_EMPTY"


class ProposalResponseInvalid(ProposalGenerationError):
    code = "PROPOSAL_RESPONSE_INVALID"


class ProposalSchemaInvalid(ProposalGenerationError):
    code = "PROPOSAL_SCHEMA_VALIDATION_FAILED"


class ProposalPersistenceError(ProposalGenerationError):
    code = "PROPOSAL_PERSIST_FAILED"


class ProposalChangeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    symbol: str | None = None
    action: str
    reason: str


class ProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    understanding: str
    expected_behavior: str
    scope: list[str] = Field(min_length=1)
    changes: list[ProposalChangeDraft] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    non_goals: list[str]
    constraints: list[str]
    acceptance: list[str] = Field(min_length=1)
    validation: list[str] = Field(min_length=1)
    user_facts: list[str]
    inferences: list[str]
    risks: list[str]


class ProposalGenerator:
    def __init__(self, session: Session, provider: LLMProvider) -> None:
        self.session = session
        self.provider = provider

    def generate(
        self,
        *,
        task_id: str,
        request: LLMRequest,
        context_package: ContextPackage | None = None,
        evidenced_paths: tuple[str, ...] = (),
    ) -> ChangeProposal:
        task = self.session.get(ChangeTask, task_id)
        if task is None:
            raise ProposalGenerationError("task not found")
        total_started = perf_counter()
        prompt_started = perf_counter()
        provider_request = _with_context(request, context_package, evidenced_paths)
        prompt_build_ms = int((perf_counter() - prompt_started) * 1000)
        LOGGER.info(
            (
                "[perf] proposal.prompt_build task_id=%s duration_ms=%s "
                "prompt_chars=%s context_chars=%s selected_files_count=%s"
            ),
            task_id,
            prompt_build_ms,
            len(provider_request.input_text),
            context_package.char_count if context_package is not None else 0,
            len(evidenced_paths),
        )
        provider_started = perf_counter()
        response = self.provider.complete(provider_request)
        provider_ms = int((perf_counter() - provider_started) * 1000)
        LOGGER.info(
            (
                "[perf] proposal.provider task_id=%s duration_ms=%s "
                "input_tokens=%s output_tokens=%s response_chars=%s"
            ),
            task_id,
            provider_ms,
            response.usage.input_tokens,
            response.usage.output_tokens,
            len(response.content),
        )
        content = response.content.strip()
        if not content:
            raise ProposalResponseEmpty("provider returned empty assistant content")
        parse_started = perf_counter()
        try:
            payload = _loads_proposal_json(content)
        except JSONDecodeError as exc:
            raise ProposalResponseInvalid("provider returned non-JSON proposal content") from exc
        try:
            draft = ProposalDraft.model_validate(payload)
        except ValidationError as exc:
            validation_errors = _validation_errors(exc)
            actual_keys = _actual_keys(payload)
            expected_keys = _expected_keys()
            LOGGER.warning(
                (
                    "PROPOSAL_SCHEMA_VALIDATION_FAILED task_id=%s errors=%s "
                    "actual_keys=%s expected_keys=%s"
                ),
                task_id,
                validation_errors,
                actual_keys,
                expected_keys,
            )
            raise ProposalSchemaInvalid(
                _schema_error_message(validation_errors),
                actual_keys=actual_keys,
                expected_keys=expected_keys,
                validation_errors=validation_errors,
            ) from exc
        parse_ms = int((perf_counter() - parse_started) * 1000)
        version = self._next_version(task_id)
        persist_started = perf_counter()
        try:
            user_decisions = _user_decisions(draft)
            proposal = ChangeProposal(
                task_id=task_id,
                version=version,
                goal=draft.goal,
                current_problem=json.dumps(
                    {
                        "understanding": draft.understanding,
                        "user_facts": draft.user_facts,
                    },
                    sort_keys=True,
                ),
                expected_behavior=draft.expected_behavior,
                initial_scope_json=json.dumps(draft.scope, sort_keys=True),
                excluded_scope_json=json.dumps(draft.non_goals, sort_keys=True),
                constraints_json=json.dumps(
                    {
                        "constraints": draft.constraints,
                        "changes": [item.model_dump() for item in draft.changes],
                        "steps": draft.steps,
                    },
                    sort_keys=True,
                ),
                assumptions_json=json.dumps(
                    {
                        "conversation": _conversation_metadata(task, request.input_text),
                        "user_facts": draft.user_facts,
                        "user_decisions": user_decisions,
                    },
                    sort_keys=True,
                ),
                risks_json=json.dumps(
                    {"inferences": draft.inferences, "risks": draft.risks},
                    sort_keys=True,
                ),
                acceptance_criteria_json=json.dumps(draft.acceptance, sort_keys=True),
                validation_plan_json=json.dumps(draft.validation, sort_keys=True),
                completeness=ProposalCompleteness.COMPLETE,
                status=ProposalStatus.DRAFT,
                created_by_type=ProposalCreatedByType.LLM,
            )
            self.session.add(proposal)
            self.session.flush()
            completeness_started = perf_counter()
            ProposalCompletenessService(self.session).evaluate(proposal.id)
            completeness_ms = int((perf_counter() - completeness_started) * 1000)
        except Exception as exc:
            raise ProposalPersistenceError("proposal persistence failed") from exc
        LOGGER.info(
            (
                "[perf] proposal.persist task_id=%s proposal_id=%s duration_ms=%s "
                "proposal_version=%s"
            ),
            task_id,
            proposal.id,
            int((perf_counter() - persist_started) * 1000),
            proposal.version,
        )
        LOGGER.info(
            (
                "[perf] proposal.total task_id=%s proposal_id=%s duration_ms=%s "
                "prompt_chars=%s context_chars=%s"
            ),
            task_id,
            proposal.id,
            int((perf_counter() - total_started) * 1000),
            len(provider_request.input_text),
            context_package.char_count if context_package is not None else 0,
        )
        LOGGER.info(
            (
                "[perf] proposal-generate provider_ms=%s parse_ms=%s completeness_ms=%s "
                "proposal.persist_ms=%s task_id=%s proposal_id=%s"
            ),
            provider_ms,
            parse_ms,
            completeness_ms,
            int((perf_counter() - persist_started) * 1000),
            task_id,
            proposal.id,
        )
        return proposal


    def _next_version(self, task_id: str) -> int:
        latest = self.session.scalars(
            select(ChangeProposal.version)
            .where(ChangeProposal.task_id == task_id)
            .order_by(ChangeProposal.version.desc())
        ).first()
        return int(latest or 0) + 1


def proposal_response_schema() -> dict[str, object]:
    return ProposalDraft.model_json_schema()


def _expected_keys() -> list[str]:
    return list(ProposalDraft.model_fields.keys())


def _loads_proposal_json(content: str) -> object:
    try:
        return json.loads(content)
    except JSONDecodeError:
        candidate = _extract_json_object(content)
        if candidate is None:
            raise
        return json.loads(candidate)


def _extract_json_object(content: str) -> str | None:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(content[index:])
        except JSONDecodeError:
            continue
        return content[index : index + end]
    return None


def _with_context(
    request: LLMRequest,
    context_package: ContextPackage | None,
    evidenced_paths: tuple[str, ...],
) -> LLMRequest:
    input_text = _proposal_prompt(
        user_request=request.input_text,
        context_package=context_package,
        evidenced_paths=evidenced_paths,
    )
    if context_package is None:
        return LLMRequest(
            prompt_summary=request.prompt_summary,
            input_text=input_text,
            timeout_seconds=request.timeout_seconds,
            cancellation_token=request.cancellation_token,
            response_schema=proposal_response_schema(),
        )
    return LLMRequest(
        prompt_summary=request.prompt_summary,
        input_text=input_text,
        timeout_seconds=request.timeout_seconds,
        cancellation_token=request.cancellation_token,
        response_schema=proposal_response_schema(),
    )


def _proposal_prompt(
    *,
    user_request: str,
    context_package: ContextPackage | None,
    evidenced_paths: tuple[str, ...],
) -> str:
    schema = proposal_response_schema()
    schema_instruction = {
        "canonical_contract": "ProposalDraft",
        "json_schema": schema,
        "required_json_fields": _expected_keys(),
        "path_rule": (
            "scope entries must be selected from evidenced_existing_paths only; "
            "choose the smallest executable frontend/source scope that can satisfy the user request"
        ),
        "evidenced_existing_paths": list(evidenced_paths),
    }
    sections = [
        "Generate a repository-specific engineering proposal.",
        "Return only one JSON object that matches the canonical ProposalDraft schema.",
        "Do not add markdown fences, explanations, comments, or extra properties.",
        "All user-facing natural-language proposal content MUST be Simplified Chinese (zh-CN).",
        "Keep user-facing zh-CN values concise: short phrases or one compact sentence per item.",
        "Keep arrays small and only include implementation-relevant evidence.",
        "Keep JSON property names and enum values unchanged. Do not translate schema keys.",
        "Use snake_case property names exactly as shown in the schema.",
        (
            "Code identifiers, file paths, API names, library names, and proper "
            "technical nouns may remain English."
        ),
        "The proposal is a scope contract for later impact analysis, governance, and execution.",
        "understanding must state how Mentor interprets the user's desired change.",
        (
            "changes must name existing repository paths from evidenced_existing_paths whenever "
            "a path is certain."
        ),
        (
            "For simple UI text changes, prefer the direct frontend source file that contains "
            "the requested text over broad app shells, docs, tests, or backend files."
        ),
        (
            "When repository context includes semantic_context, prefer paths whose semantic "
            "role matches the user's location or component wording, such as sidebar, "
            "navigation, menu-item, button, or page-heading."
        ),
        "Each change must explain the intended modification and why it belongs in scope.",
        "steps must be concrete implementation steps, not one-line generic workflow filler.",
        "risks must name likely impact/risk areas from the repository context.",
        "validation must state concrete checks the finished change should pass.",
        (
            "If a required list has no positive items, return an empty array rather than "
            "omitting the property."
        ),
        (
            "Do not invent files. If exact files are uncertain, choose the nearest real "
            "candidate source path and let execution-phase SEARCH_CODE/READ_FILE localize "
            "the exact line."
        ),
        (
            "Do not include UNKNOWN/TBD/TODO placeholder risks when evidenced_existing_paths "
            "contains a plausible real source candidate."
        ),
        f"User request: {user_request}",
        f"Schema contract: {json.dumps(schema_instruction, ensure_ascii=False, sort_keys=True)}",
    ]
    if context_package is not None:
        sections.extend(["Repository context:", context_package.render()])
    return "\n".join(sections)


def _conversation_metadata(task: ChangeTask, input_text: str) -> dict[str, str | None]:
    original = task.original_request
    follow_up = None
    marker = "Follow-up instruction:"
    if marker in input_text:
        follow_up = input_text.split(marker, 1)[1].strip()
    return {
        "original_request": original,
        "proposal_input": input_text,
        "follow_up_instruction": follow_up,
    }


def _user_decisions(draft: ProposalDraft) -> list[str]:
    candidates = [*draft.constraints, *draft.inferences, *draft.risks]
    decisions: list[str] = []
    decision_markers = (
        "user decision",
        "product decision",
        "ask user",
        "confirm whether",
        "needs user",
        "用户决定",
        "产品决策",
        "需要用户",
        "由用户",
        "是否包含",
        "是否允许",
        "是否公开",
    )
    technical_markers = (
        "api",
        "dto",
        "test",
        "frontend",
        "backend",
        "database",
        "schema",
        "module",
        "dependency",
        "接口",
        "测试",
        "前端",
        "后端",
        "数据库",
        "依赖",
        "模块",
        "文件",
    )
    for item in candidates:
        text = str(item).strip()
        lowered = text.lower()
        if not text or not any(marker in lowered for marker in decision_markers):
            continue
        if any(marker in lowered for marker in technical_markers):
            continue
        decisions.append(text)
    return list(dict.fromkeys(decisions))


def _actual_keys(payload: object) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload)
    return []


def _validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in exc.errors():
        loc = item.get("loc", ())
        path = ".".join(str(part) for part in loc) if loc else "<root>"
        errors.append(
            {
                "path": path,
                "type": str(item.get("type", "validation_error")),
                "message": str(item.get("msg", "schema validation failed")),
            }
        )
    return errors


def _schema_error_message(validation_errors: list[dict[str, str]]) -> str:
    missing = [item["path"] for item in validation_errors if item.get("type") == "missing"]
    if missing:
        return f"Proposal response missing required field(s): {', '.join(missing)}"
    locations = [item["path"] for item in validation_errors]
    if locations:
        return f"Proposal response failed schema validation at: {', '.join(locations)}"
    return "Proposal response failed schema validation"
