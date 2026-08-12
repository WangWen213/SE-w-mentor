from __future__ import annotations

import json

QUESTION_ANSWER_FAILURE = "回答生成失败，请重试。"


def workbench_message_text(*, role: str, kind: str, text: str) -> str:
    stripped = text.strip()
    if role != "MENTOR":
        return stripped
    if kind == "TEXT":
        return _mentor_text(stripped)
    if kind == "PROPOSAL":
        return _proposal_intro(stripped)
    if kind == "ERROR":
        return _error_text(stripped)
    return stripped


def _mentor_text(text: str) -> str:
    payload = _json_object(text)
    if payload is None:
        return text
    answer = payload.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return QUESTION_ANSWER_FAILURE


def _proposal_intro(text: str) -> str:
    payload = _json_object(text)
    if payload is None:
        return text
    return "我已经更新了当前方案，请查看下方 Proposal 卡片。"


def _error_text(text: str) -> str:
    payload = _json_object(text)
    if payload is None:
        return text
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "操作失败，请重试。"


def _json_object(text: str) -> dict[str, object] | None:
    candidate = _json_payload_text(text)
    if candidate is None:
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _json_payload_text(text: str) -> str | None:
    if text.startswith("{"):
        return text
    if not text.startswith("```"):
        return None
    lines = text.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return None
    fence = lines[0].strip().lower()
    if fence not in {"```", "```json"}:
        return None
    body = "\n".join(lines[1:-1]).strip()
    return body if body.startswith("{") else None
