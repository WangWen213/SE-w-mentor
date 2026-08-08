from __future__ import annotations


class RefreshQueue:
    def __init__(self) -> None:
        self._items: list[str] = []

    def enqueue(self, knowledge_id: str) -> None:
        if knowledge_id not in self._items:
            self._items.append(knowledge_id)

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(self._items)
