from __future__ import annotations

from pathlib import Path

from se_mentor.readers.file_reader import RepositoryReader


def test_T029_read_search_reject_sensitive_and_return_line_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("alpha\nneedle()\nneedle()\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / "blob.bin").write_bytes(b"\x00\x01")
    reader = RepositoryReader(repo, max_read_bytes=12, max_search_results=2)

    listing = reader.list_directory("src")
    assert [item.relative_path for item in listing.entries] == ["src/app.py"]

    read = reader.read_file("src/app.py")
    assert read.evidence.relative_path == "src/app.py"
    assert read.lines[0].line_number == 1
    assert read.truncated is True

    rejected = reader.read_file(".env")
    assert rejected.status == "REJECTED"
    assert rejected.reason == "SENSITIVE_FILE"

    binary = reader.read_file("blob.bin")
    assert binary.status == "BINARY"
    assert binary.content == ""

    search = reader.search_code("needle")
    assert [hit.line_number for hit in search.hits] == [2, 3]
    assert all(hit.evidence_ref.relative_path == "src/app.py" for hit in search.hits)
    assert search.truncated is False
