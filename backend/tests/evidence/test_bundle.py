from __future__ import annotations

import pytest
from phase1_test_helpers import REVISION

from se_mentor.evidence.bundle import (
    EvidenceBundleBuilder,
    EvidenceBundleError,
    EvidenceItem,
)


def test_T042_bundle_rejects_missing_or_cross_revision_evidence() -> None:
    current = EvidenceItem(
        evidence_id="code:api",
        kind="code",
        revision=REVISION,
        uri="source://backend/src/app/api.py",
        summary="API symbol indexed",
        freshness="fresh",
        confidence="confirmed",
        verified=True,
    )
    stale = EvidenceItem(
        evidence_id="knowledge:old",
        kind="knowledge",
        revision="older-revision",
        uri="knowledge://old",
        summary="Old knowledge",
        freshness="stale",
        confidence="uncertain",
        verified=False,
    )
    builder = EvidenceBundleBuilder([current, stale])

    bundle = builder.build(
        task_id="task-1",
        revision=REVISION,
        required_refs=("code:api",),
        unresolved_assumptions=("manual approval pending",),
    )

    same_bundle = builder.build(
        task_id="task-1",
        revision=REVISION,
        required_refs=("code:api",),
        unresolved_assumptions=("manual approval pending",),
    )

    assert bundle.bundle_hash == same_bundle.bundle_hash
    assert bundle.items == (current,)
    assert bundle.unresolved_assumptions == ("manual approval pending",)

    with pytest.raises(EvidenceBundleError, match="missing"):
        builder.build(task_id="task-1", revision=REVISION, required_refs=("missing",))

    with pytest.raises(EvidenceBundleError, match="cross_revision"):
        builder.build(task_id="task-1", revision=REVISION, required_refs=("knowledge:old",))
