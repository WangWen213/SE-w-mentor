from __future__ import annotations

import json

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from se_mentor.api.envelope import error, ok
from se_mentor.api.runtime import get_domain_provider, get_session_factory
from se_mentor.db.session import session_scope
from se_mentor.llm.base import LLMRequest, ProviderError
from se_mentor.models.governance import GovernanceDecision, GovernanceDecisionStatus, ImpactReport, ImpactReportStatus
from se_mentor.models.knowledge import EngineeringKnowledge
from se_mentor.models.task import ChangeProposal, ChangeTask, ProposalStatus
from se_mentor.models.workbench import WorkbenchMessage
from se_mentor.api.workbench_presentation import QUESTION_ANSWER_FAILURE, workbench_message_text

router = APIRouter(prefix="/api/tasks/{task_id}/turns", tags=["mentor-turns"])
_SESSION_FACTORY = get_session_factory()


class MentorTurnCreate(BaseModel):
    text: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_turn(task_id: str, payload: MentorTurnCreate, response: Response) -> dict[str, object]:
    user_text = payload.text.strip()
    if not user_text:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return error("MENTOR_TURN_TEXT_REQUIRED", "turn text is required")
    with session_scope(_SESSION_FACTORY) as session:
        task = session.get(ChangeTask, task_id)
        if task is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return error("TASK_NOT_FOUND", "task not found")
        proposal = _active_or_latest_proposal(session, task_id)
        turn_type = _route_turn(user_text, proposal)
        if turn_type == "PROPOSAL_REVISION":
            return ok({"type": "PROPOSAL_REVISION", "message": None, "proposal": None})
        _add_workbench_message(
            session,
            task_id=task_id,
            role="USER",
            kind="TEXT",
            status="DONE",
            text=user_text,
        )
        answer = (
            _continue_analysis_answer(session, proposal)
            if turn_type == "CONTINUE_TECHNICAL_ANALYSIS" and proposal is not None
            else _answer_question(session, task, proposal, user_text)
        )
        mentor_message = _add_workbench_message(
            session,
            task_id=task_id,
            role="MENTOR",
            kind="TEXT",
            status="DONE",
            text=answer,
        )
        return ok({"type": "ANSWER", "message": _message_payload(mentor_message), "proposal": None})


def _route_turn(user_text: str, proposal: ChangeProposal | None) -> str:
    if proposal is None:
        return "CHANGE_REQUEST"
    if _looks_like_continue_analysis(user_text):
        return "CONTINUE_TECHNICAL_ANALYSIS"
    if _looks_like_revision_request(user_text):
        return "PROPOSAL_REVISION"
    if _looks_like_question(user_text):
        return "QUESTION"
    return "QUESTION"


def _looks_like_question(value: str) -> bool:
    stripped = value.strip()
    if stripped.endswith(("?", "？")):
        return True
    question_markers = (
        "什么",
        "哪些",
        "哪个",
        "是否",
        "是不是",
        "有没有",
        "怎么",
        "为什么",
        "还有",
        "能否",
        "可以吗",
        "范围",
        "影响",
        "风险",
        "遗漏",
        "做到哪里",
        "进展",
        "当前状态",
    )
    return any(marker in stripped for marker in question_markers)


def _looks_like_revision_request(value: str) -> bool:
    revision_markers = (
        "加入方案",
        "加进方案",
        "纳入方案",
        "更新方案",
        "修改方案",
        "调整方案",
        "按这个改",
        "把它加",
        "也加",
        "也做",
        "改成",
        "调整为",
        "增加",
        "新增",
        "删除",
        "移除",
        "不允许",
        "不能",
    )
    return any(marker in value for marker in revision_markers)


def _looks_like_continue_analysis(value: str) -> bool:
    markers = (
        "继续分析",
        "继续核实",
        "继续看",
        "继续查",
        "再分析",
        "深入分析",
        "then continue analysis",
        "continue analysis",
    )
    return any(marker in value.lower() for marker in markers)


def _continue_analysis_answer(session, proposal: ChangeProposal) -> str:
    impact = session.scalar(
        select(ImpactReport)
        .where(ImpactReport.proposal_id == proposal.id)
        .where(ImpactReport.status == ImpactReportStatus.CURRENT)
        .order_by(ImpactReport.created_at.desc())
    )
    if proposal.completeness != "COMPLETE":
        return (
            "我会继续补全当前 Proposal 的技术分析，但不会因为这句话创建新的 v1 方案。\n\n"
            "当前还不能确认范围的原因，是 Proposal 里仍有 Mentor 应该自行补齐的技术细节。"
        )
    if impact is None:
        return (
            "当前 Proposal 的主要修改范围已经完整。\n\n"
            "你刚才提到的继续分析，属于确认范围后的正式影响分析阶段。我会在该阶段继续核实性能、数据兼容、安全和依赖影响，不需要你现在逐项确认，也不会创建新的 Proposal。"
        )
    unknowns = _as_string_list(_json_object(impact.uncertainties_json).get("unknowns"))
    return (
        "我会沿当前 Proposal 继续核实已有影响分析里的未决项。\n\n"
        f"当前仍需深入核实：{_join_or_waiting(unknowns)}。\n\n"
        "这不会创建新的 Proposal，也不会重置当前版本。"
    )


def _answer_question(
    session,
    task: ChangeTask,
    proposal: ChangeProposal | None,
    user_text: str,
) -> str:
    if proposal is None:
        return (
            "我已经收到你的问题，但当前还没有可引用的 Proposal。\n\n"
            "建议下一步\n"
            "- 先创建一个 Proposal，我再基于它回答范围、影响或验证问题。"
        )

    selected = _select_question_context(session, task, proposal, user_text)
    return _generate_question_answer(user_text, selected)


def _select_question_context(
    session,
    task: ChangeTask,
    proposal: ChangeProposal,
    user_text: str,
) -> list[dict[str, object]]:
    candidates = [
        _task_context(task, proposal),
        *_memory_contexts(session, task.project_id),
        _proposal_context(session, proposal),
    ]
    scored = [(candidate, _relevance_score(user_text, candidate)) for candidate in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)
    selected = [candidate for candidate, score in scored if score > 0][:3]
    return selected or [candidates[0]]


def _task_context(task: ChangeTask, proposal: ChangeProposal) -> dict[str, object]:
    return {
        "kind": "task",
        "title": "当前任务状态",
        "keywords": "任务 状态 进展 做到哪里 当前 完成 阶段 status task",
        "facts": [
            f"任务状态：{task.status}",
            f"原始需求：{task.original_request}",
            f"当前 Proposal：v{proposal.version}，状态 {_proposal_phase(proposal)}",
        ],
    }


def _memory_contexts(session, project_id: str) -> list[dict[str, object]]:
    rows = session.scalars(
        select(EngineeringKnowledge)
        .where(EngineeringKnowledge.project_id == project_id)
        .order_by(EngineeringKnowledge.created_at.desc())
    ).all()
    facts = [
        "项目记忆页展示后端 knowledge repository 中的 EngineeringKnowledge 条目。",
        "项目记忆会记录知识 key、类型、状态、摘要、作用范围和 evidence refs。",
        "Project Understanding 条目会从索引证据中整理技术栈、模块、关键路径、测试框架、风险和结构化详情。",
        "记忆更新来自项目理解、成功经验、失败经验和人工复核后的知识沉淀。",
    ]
    for row in rows[:6]:
        facts.append(f"{row.knowledge_key}: {row.summary}")
    return [
        {
            "kind": "memory",
            "title": "项目记忆功能",
            "keywords": "项目记忆 记忆 memory knowledge engineeringknowledge 学习 展示 更新 evidence 项目理解 模块 技术栈",
            "facts": facts,
        },
        {
            "kind": "project",
            "title": "项目理解",
            "keywords": "项目 模块 核心模块 代码 仓库 技术栈 project understanding index repository",
            "facts": facts,
        },
    ]


def _proposal_context(session, proposal: ChangeProposal) -> dict[str, object]:
    impact = session.scalar(
        select(ImpactReport)
        .where(ImpactReport.proposal_id == proposal.id)
        .where(ImpactReport.status == ImpactReportStatus.CURRENT)
        .order_by(ImpactReport.created_at.desc())
    )
    decision = None
    if impact is not None:
        decision = session.scalar(
            select(GovernanceDecision)
            .where(GovernanceDecision.impact_report_id == impact.id)
            .where(GovernanceDecision.status == GovernanceDecisionStatus.ACTIVE)
            .order_by(GovernanceDecision.created_at.desc())
        )
    facts = [
        f"Proposal v{proposal.version}：{proposal.goal}",
        f"预期行为：{proposal.expected_behavior}",
        f"范围：{_join_or_waiting(_json_list(proposal.initial_scope_json))}",
        f"验证：{_join_or_waiting(_json_list(proposal.validation_plan_json))}",
    ]
    if impact is not None:
        unknowns = _as_string_list(_json_object(impact.uncertainties_json).get("unknowns"))
        facts.append(f"影响分析未知项：{_join_or_waiting(unknowns)}")
    if decision is not None:
        facts.append(f"治理结论：{decision.decision}，{decision.reason_summary}")
    return {
        "kind": "proposal",
        "title": "当前 Proposal",
        "keywords": "proposal 方案 风险 影响 范围 验证 治理 当前proposal risk impact scope governance",
        "facts": facts,
    }


def build_question_answer_input(user_text: str, contexts: list[dict[str, object]]) -> str:
    sections = [
        "CURRENT USER QUESTION:",
        user_text,
        "",
        "Instruction:",
        "First answer the current user's question directly.",
        "Use repository/task/proposal context only as supporting evidence.",
        "Do not replace the user's question with the current proposal topic.",
        "Answer in Simplified Chinese.",
        "",
        "SUPPORTING CONTEXT:",
    ]
    for context in contexts:
        sections.append(f"[{context['kind']}] {context['title']}")
        for fact in context["facts"]:
            sections.append(f"- {fact}")
    return "\n".join(sections)


def _generate_question_answer(user_text: str, contexts: list[dict[str, object]]) -> str:
    prompt = build_question_answer_input(user_text, contexts)
    try:
        response = get_domain_provider().complete(
            LLMRequest(
                prompt_summary="mentor_question_answer",
                input_text=prompt,
                timeout_seconds=60,
            )
        )
    except ProviderError:
        return _fallback_answer_from_current_query(prompt, contexts)
    return workbench_message_text(role="MENTOR", kind="TEXT", text=response.content) or QUESTION_ANSWER_FAILURE


def _user_facing_question_answer(content: str) -> str:
    return workbench_message_text(role="MENTOR", kind="TEXT", text=content)


def _fallback_answer_from_current_query(prompt: str, contexts: list[dict[str, object]]) -> str:
    primary = str(contexts[0]["kind"])
    if primary == "memory":
        return _memory_answer(prompt, contexts[0])
    if primary == "project":
        return _project_answer(prompt, contexts[0])
    if primary == "proposal":
        return _proposal_answer(prompt, contexts[0])
    return _task_answer(prompt, contexts[0])


def _memory_answer(prompt: str, context: dict[str, object]) -> str:
    return "\n".join(
        [
            "项目记忆功能主要展示 Mentor 已经沉淀下来的工程知识，而不是当前 Proposal 本身。",
            "",
            "能展示什么",
            "- 知识条目的 key、类型、状态和摘要。",
            "- 每条记忆关联的作用范围和证据引用。",
            "- Project Understanding 中整理出的技术栈、核心模块、关键路径、测试框架和风险提示。",
            "",
            "会学习什么",
            "- 仓库结构、入口路径、重要模块和测试工具。",
            "- 已验证的工程约束、决策、模式，以及成功或失败经验。",
            "- 后续任务执行后的结果证据，用于更新或修正已有记忆。",
            "",
            "当前限制",
            "- 记忆只应基于已索引或已验证的证据更新，不能把一次对话里的猜测直接当成事实。",
            "- 如果索引证据不足，展示内容会偏候选态，需要人工复核。",
            "",
            _supporting_note(prompt),
        ]
    )


def _project_answer(prompt: str, context: dict[str, object]) -> str:
    facts = [str(item) for item in context["facts"]][:5]
    return "\n".join(
        [
            "当前项目问题应优先看项目理解和记忆证据。",
            "",
            "可用上下文",
            *[f"- {fact}" for fact in facts],
            "",
            "建议下一步",
            "- 打开项目记忆页查看 Project Understanding 是否已经足够；如果不足，需要先补充索引证据。",
            "",
            _supporting_note(prompt),
        ]
    )


def _proposal_answer(prompt: str, context: dict[str, object]) -> str:
    facts = [str(item) for item in context["facts"]][:6]
    return "\n".join(
        [
            "这个问题与当前 Proposal 相关，所以我会用 Proposal、影响分析和治理状态作答。",
            "",
            "当前依据",
            *[f"- {fact}" for fact in facts],
            "",
            "建议下一步",
            "- 如果这些风险或范围不符合你的预期，可以明确提出要加入或修改方案。",
            "",
            _supporting_note(prompt),
        ]
    )


def _task_answer(prompt: str, context: dict[str, object]) -> str:
    facts = [str(item) for item in context["facts"]][:5]
    return "\n".join(
        [
            "当前任务进展应以任务状态、Proposal 状态、治理和执行状态为准。",
            "",
            "当前状态",
            *[f"- {fact}" for fact in facts],
            "",
            "建议下一步",
            "- 如果 Proposal 仍是草稿，下一步通常是确认范围；确认后才会进入影响分析、治理和执行。",
            "",
            _supporting_note(prompt),
        ]
    )


def _supporting_note(prompt: str) -> str:
    query = prompt.split("CURRENT USER QUESTION:", 1)[1].split("Instruction:", 1)[0].strip()
    return f"我本轮回答的是当前问题：“{query}”。"


def _relevance_score(user_text: str, context: dict[str, object]) -> int:
    query_tokens = _tokens(user_text)
    context_tokens = _tokens(" ".join([str(context["title"]), str(context["keywords"]), *map(str, context["facts"])]))
    return len(query_tokens & context_tokens)


def _tokens(value: str) -> set[str]:
    lowered = value.lower()
    ascii_parts = {part for part in lowered.replace("_", " ").replace("-", " ").split() if len(part) >= 2}
    cjk_chars = {char for char in lowered if "\u4e00" <= char <= "\u9fff"}
    cjk_bigrams = {lowered[index : index + 2] for index in range(len(lowered) - 1) if all("\u4e00" <= char <= "\u9fff" for char in lowered[index : index + 2])}
    return ascii_parts | cjk_chars | cjk_bigrams


def _proposal_phase(proposal: ChangeProposal) -> str:
    if proposal.status == ProposalStatus.DRAFT:
        return "方案确认阶段"
    if proposal.status == ProposalStatus.CONFIRMED:
        return "范围已确认阶段"
    if proposal.status == ProposalStatus.REJECTED:
        return "方案已取消阶段"
    return "方案复核阶段"


def _active_or_latest_proposal(session, task_id: str) -> ChangeProposal | None:
    task = session.get(ChangeTask, task_id)
    if task is not None and task.active_proposal_id:
        proposal = session.get(ChangeProposal, task.active_proposal_id)
        if proposal is not None and proposal.status != ProposalStatus.SUPERSEDED:
            return proposal
    return session.scalar(
        select(ChangeProposal)
        .where(ChangeProposal.task_id == task_id)
        .where(ChangeProposal.status != ProposalStatus.SUPERSEDED)
        .order_by(ChangeProposal.version.desc())
    )


def _add_workbench_message(
    session,
    *,
    task_id: str,
    role: str,
    kind: str,
    status: str,
    text: str,
) -> WorkbenchMessage:
    sequence = int(
        session.scalar(
            select(func.coalesce(func.max(WorkbenchMessage.sequence), 0))
            .where(WorkbenchMessage.task_id == task_id)
        )
        or 0
    ) + 1
    message = WorkbenchMessage(
        task_id=task_id,
        sequence=sequence,
        role=role,
        kind=kind,
        status=status,
        text=workbench_message_text(role=role, kind=kind, text=text),
    )
    session.add(message)
    session.flush()
    return message


def _message_payload(message: WorkbenchMessage) -> dict[str, object]:
    return {
        "createdAt": message.created_at.isoformat(),
        "id": message.id,
        "kind": message.kind,
        "proposal": None,
        "role": message.role,
        "sequence": message.sequence,
        "status": message.status,
        "taskId": message.task_id,
        "text": message.text,
    }


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _join_or_waiting(values: list[str]) -> str:
    return "、".join(values[:6]) if values else "待补充"
