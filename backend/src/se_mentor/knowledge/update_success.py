from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from se_mentor.knowledge.signature import CodeKnowledgeSignature, KnowledgeSignatureBuilder
from se_mentor.models.knowledge import KnowledgeStatus


@dataclass(frozen=True)
class SuccessfulTaskResult:
    task_id: str
    revision: str
    committed_diff: str
    changed_paths: tuple[str, ...]
    passed_validation_refs: tuple[str, ...]
    final_summary: str


@dataclass(frozen=True)
class SuccessKnowledgeRecord:
    task_id: str
    relative_path: str
    summary: str
    status: KnowledgeStatus
    signature: CodeKnowledgeSignature
    evidence_refs: tuple[str, ...]


class SuccessKnowledgeUpdater:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.signature_builder = KnowledgeSignatureBuilder(self.project_root)

    def extract(self, result: SuccessfulTaskResult) -> list[SuccessKnowledgeRecord]:
        evidence_refs = tuple(ref for ref in result.passed_validation_refs if ref.strip())
        if not result.committed_diff.strip() or not evidence_refs:
            return []

        records: list[SuccessKnowledgeRecord] = []
        for relative_path in result.changed_paths:
            if not _path_appears_in_diff(relative_path, result.committed_diff):
                continue
            signature = self.signature_builder.for_file(relative_path, revision=result.revision)
            records.append(
                SuccessKnowledgeRecord(
                    task_id=result.task_id,
                    relative_path=signature.relative_path,
                    summary=result.final_summary,
                    status=KnowledgeStatus.VERIFIED,
                    signature=signature,
                    evidence_refs=evidence_refs,
                )
            )
        return records


def _path_appears_in_diff(relative_path: str, diff_text: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized in diff_text or diff_text.strip().startswith(("+", "-"))
