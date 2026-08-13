from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI_FILE = ROOT / ".gitlab-ci.yml"
RESERVED_TOP_LEVEL_KEYS = {
    "after_script",
    "before_script",
    "cache",
    "default",
    "image",
    "include",
    "stages",
    "variables",
    "workflow",
}


def read_ci() -> str:
    return CI_FILE.read_text(encoding="utf-8")


def top_level_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def job_blocks() -> dict[str, str]:
    return {
        name: block
        for name, block in top_level_blocks(read_ci()).items()
        if name not in RESERVED_TOP_LEVEL_KEYS and not name.startswith(".")
    }


def test_gitlab_ci_file_exists() -> None:
    assert CI_FILE.exists()


def test_required_jobs_are_present() -> None:
    jobs = job_blocks()
    assert "unit-test" in jobs
    assert {
        "backend-build",
        "frontend-build",
        "frontend-test",
        "migration",
        "mock-e2e",
        "quality",
        "release-gate",
        "secret-scan",
        "security",
    }.issubset(jobs)


def test_critical_jobs_block_pipeline() -> None:
    ci = read_ci()
    assert "allow_failure: true" not in ci
    assert "|| true" not in ci


def test_backend_frontend_and_e2e_commands_are_wired() -> None:
    jobs = job_blocks()
    assert "scripts/ci/run_backend_tests.py" in jobs["unit-test"]
    assert "npm run type-check" in jobs["frontend-test"]
    assert "npm run test -- --run" in jobs["frontend-test"]
    assert "scripts/ci/run_mock_e2e.py" in jobs["mock-e2e"]


def test_security_migration_secret_and_build_gates_are_wired() -> None:
    jobs = job_blocks()
    assert "scripts/ci/run_security_checks.py" in jobs["security"]
    assert "scripts/ci/scan_secrets.py" in jobs["secret-scan"]
    assert "scripts/ci/check_migrations.py" in jobs["migration"]
    assert "python -m build backend" in jobs["backend-build"]
    assert "npm run build" in jobs["frontend-build"]


def test_release_gate_is_protected_and_contract_only() -> None:
    release_gate = job_blocks()["release-gate"]
    assert "CI_COMMIT_REF_PROTECTED" in release_gate
    assert "when: never" in release_gate
    assert "DEPLOY_IMAGE_TAG" in release_gate
    assert "CI_COMMIT_SHA" in release_gate
    assert "latest" in release_gate
    assert "DEPLOY_HEALTHCHECK_URL" in release_gate
    assert "ROLLBACK_RUNBOOK_URL" in release_gate


def test_pipeline_uses_immutable_commit_sha_tag_contract() -> None:
    ci = read_ci()
    assert 'DEPLOY_IMAGE_TAG: "$CI_COMMIT_SHA"' in ci
    assert not re.search(r"(?im)^\s*(image_tag|deploy_image_tag):\s*latest\s*$", ci)


def test_ci_files_do_not_embed_secret_literals() -> None:
    ci = read_ci()
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", ci)
    assert "-----BEGIN" not in ci
    assert not re.search(r"\bAKIA[0-9A-Z]{16}\b", ci)
