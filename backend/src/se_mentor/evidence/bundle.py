from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from collections.abc import Iterable


class EvidenceBundleError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    kind: str
    revision: str
    uri: str
    summary: str
    freshness: str
    confidence: str
    verified: bool


@dataclass(frozen=True)
class EvidenceBundle:
    task_id: str
    revision: str
    items: tuple[EvidenceItem, ...]
    unresolved_assumptions: tuple[str, ...]
    bundle_hash: str


class EvidenceBundleBuilder:
    def __init__(self, evidence_items: Iterable[EvidenceItem]) -> None:
        self._items = {item.evidence_id: item for item in evidence_items}

    def build(
        self,
        *,
        task_id: str,
        revision: str,
        required_refs: Iterable[str],
        unresolved_assumptions: Iterable[str] = (),
    ) -> EvidenceBundle:
        required = tuple(required_refs)
        missing = tuple(ref for ref in required if ref not in self._items)
        if missing:
            raise EvidenceBundleError(f"missing evidence refs: {', '.join(missing)}")
        items = tuple(self._items[ref] for ref in required)
        cross_revision = tuple(item.evidence_id for item in items if item.revision != revision)
        if cross_revision:
            raise EvidenceBundleError(
                f"cross_revision evidence refs: {', '.join(cross_revision)}"
            )
        assumptions = tuple(sorted(str(item) for item in unresolved_assumptions if str(item)))
        ordered_items = tuple(sorted(items, key=lambda item: item.evidence_id))
        bundle_hash = _bundle_hash(task_id, revision, ordered_items, assumptions)
        return EvidenceBundle(task_id, revision, ordered_items, assumptions, bundle_hash)


def _bundle_hash(
    task_id: str,
    revision: str,
    items: tuple[EvidenceItem, ...],
    assumptions: tuple[str, ...],
) -> str:
    payload = {
        "task_id": task_id,
        "revision": revision,
        "items": [asdict(item) for item in items],
        "unresolved_assumptions": assumptions,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
