from __future__ import annotations

from pathlib import Path

from se_mentor.knowledge.signature import KnowledgeSignatureBuilder, SignatureStatus


def test_T036_comment_only_change_keeps_ast_signature_but_logic_change_does_not(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "service.py"
    target.write_text("def answer():\n    return 1\n", encoding="utf-8")
    builder = KnowledgeSignatureBuilder(repo)

    original = builder.for_file("service.py", revision="r1", symbol_name="answer")
    target.write_text("# comment only\n\ndef answer():\n    return 1\n", encoding="utf-8")
    comment_only = builder.for_file("service.py", revision="r2", symbol_name="answer")
    target.write_text("def answer():\n    return 2\n", encoding="utf-8")
    changed = builder.for_file("service.py", revision="r3", symbol_name="answer")
    target.write_text("def broken(:\n", encoding="utf-8")
    degraded = builder.for_file("service.py", revision="r4", symbol_name="answer")
    target.write_text("def answer():\n    return 2\n", encoding="utf-8")
    missing = builder.for_file("service.py", revision="r5", symbol_name="missing")
    outside = builder.for_file("../outside.py", revision="r6")

    assert original.status is SignatureStatus.OK
    assert original.ast_hash == comment_only.ast_hash
    assert original.symbol_hash == comment_only.symbol_hash
    assert original.ast_hash != changed.ast_hash
    assert original.symbol_hash != changed.symbol_hash
    assert degraded.status is SignatureStatus.DEGRADED_PARSE_ERROR
    assert degraded.ast_hash is None
    assert missing.status is SignatureStatus.MISSING_SYMBOL
    assert outside.status is SignatureStatus.OUTSIDE_PROJECT
    assert len(original.file_hash) == 64
    assert original.revision == "r1"
