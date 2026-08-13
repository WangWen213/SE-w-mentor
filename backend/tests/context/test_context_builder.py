from __future__ import annotations

from se_mentor.context.context_builder import ContextBuilder, ContextItem, TrustLabel


def test_AC_FR03_01_context_is_minimal_and_preserves_governance_content() -> None:
    noisy_files = tuple(
        ContextItem(
            item_id=f"file-{index}",
            section="code",
            text="unrelated implementation detail " * 80,
            priority=10,
            trust_label=TrustLabel.REPOSITORY_CONTENT,
        )
        for index in range(8)
    )
    package = ContextBuilder(max_chars=900).build(
        goal="Fix audit logging",
        governance_items=(
            ContextItem(
                item_id="deny-env",
                section="governance",
                text="DENY_HARD .env writes",
                priority=100,
                trust_label=TrustLabel.SYSTEM,
            ),
        ),
        execution_policy=ContextItem(
            item_id="policy-1",
            section="policy",
            text='{"write_paths":["backend/src/app/audit.py"]}',
            priority=95,
            trust_label=TrustLabel.SYSTEM,
        ),
        current_error=ContextItem(
            item_id="error-1",
            section="feedback",
            text="pytest failed: missing audit record",
            priority=90,
            trust_label=TrustLabel.TOOL_OUTPUT,
        ),
        repository_items=noisy_files,
        knowledge_items=(),
    )

    included_ids = {item.item_id for item in package.items}
    assert {"deny-env", "policy-1", "error-1"}.issubset(included_ids)
    assert package.char_count <= 900
    assert all(
        item.trust_label == TrustLabel.UNTRUSTED_DATA
        for item in package.items
        if item.section == "code"
    )
    assert package.dropped
    assert all(drop.reason == "budget" for drop in package.dropped)
    assert "api_key" not in package.render()
