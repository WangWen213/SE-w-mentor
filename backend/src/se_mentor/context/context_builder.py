from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class TrustLabel(StrEnum):
    SYSTEM = "SYSTEM"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    REPOSITORY_CONTENT = "REPOSITORY_CONTENT"
    UNTRUSTED_DATA = "UNTRUSTED_DATA"


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    section: str
    text: str
    priority: int
    trust_label: TrustLabel


@dataclass(frozen=True)
class DroppedContextItem:
    item_id: str
    reason: str


@dataclass(frozen=True)
class ContextPackage:
    goal: str
    items: tuple[ContextItem, ...]
    dropped: tuple[DroppedContextItem, ...]
    char_count: int

    def render(self) -> str:
        lines = [f"goal: {_redact(self.goal)}"]
        for item in self.items:
            lines.append(
                f"[{item.section}:{item.trust_label}] {item.item_id}\n{_redact(item.text)}"
            )
        return "\n\n".join(lines)


class ContextBuilder:
    def __init__(self, *, max_chars: int) -> None:
        self.max_chars = max_chars

    def build(
        self,
        *,
        goal: str,
        governance_items: tuple[ContextItem, ...],
        execution_policy: ContextItem,
        current_error: ContextItem,
        repository_items: tuple[ContextItem, ...],
        knowledge_items: tuple[ContextItem, ...],
    ) -> ContextPackage:
        mandatory = (*governance_items, execution_policy, current_error)
        included = list(mandatory)
        dropped: list[DroppedContextItem] = []
        current_size = _package_size(goal, included)
        optional = sorted(
            (*knowledge_items, *(_untrusted(item) for item in repository_items)),
            key=lambda item: (-item.priority, item.item_id),
        )
        for item in optional:
            next_size = current_size + len(item.text) + len(item.item_id) + len(item.section) + 8
            if next_size > self.max_chars:
                dropped.append(DroppedContextItem(item.item_id, "budget"))
                continue
            included.append(item)
            current_size = next_size
        return ContextPackage(goal, tuple(included), tuple(dropped), _package_size(goal, included))


def _untrusted(item: ContextItem) -> ContextItem:
    if item.trust_label == TrustLabel.REPOSITORY_CONTENT:
        return ContextItem(
            item.item_id,
            item.section,
            item.text,
            item.priority,
            TrustLabel.UNTRUSTED_DATA,
        )
    return item


def _package_size(goal: str, items: list[ContextItem]) -> int:
    return len(goal) + sum(len(item.text) + len(item.item_id) + len(item.section) for item in items)


def _redact(value: str) -> str:
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)\s*=\s*[^,\s;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )
