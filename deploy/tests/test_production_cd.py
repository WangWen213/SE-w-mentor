from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_production.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CD_WORKFLOW = ROOT / ".github" / "workflows" / "production-deploy.yml"
RUNBOOK = ROOT / "docs" / "PRODUCTION_CD_RUNBOOK.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_production_deploy_script_preserves_online_safe_runtime_contract() -> None:
    script = read(DEPLOY_SCRIPT)
    assert "git merge --ff-only origin/main" in script
    assert "git reset --hard" not in script
    assert "git clean" not in script
    assert "docker compose down -v" not in script
    assert "[ \"${SE_MENTOR_RUNTIME_PROFILE:-}\" = \"ONLINE_SAFE\" ]" in script
    assert "[ \"${SE_MENTOR_TRUST_PROXY:-}\" = \"true\" ]" in script
    assert "fullchain.pem" in script
    assert "privkey.pem" in script
    assert "compose build backend frontend" in script
    assert "compose up -d --no-build backend frontend gateway" in script
    assert "alembic" not in script
    assert "SECONDS" not in script


def test_production_deploy_script_has_health_and_runtime_gates() -> None:
    script = read(DEPLOY_SCRIPT)
    assert "https://47.76.106.57/health" in script
    assert '"status"[[:space:]]*:[[:space:]]*"ok"' in script
    assert '"profile"[[:space:]]*:[[:space:]]*"ONLINE_SAFE"' in script
    assert '"source"[[:space:]]*:[[:space:]]*"(ONLINE_SAFE|ONLINE_SAFE_SESSION)"' in script
    assert '"provider"[[:space:]]*:[[:space:]]*"OpenAI"' in script
    assert "CLOUD_DEMO/Mock" in script
    assert "SE_MENTOR_RUNTIME_PROFILE\" = ONLINE_SAFE" in script
    assert "SE_MENTOR_TRUST_PROXY\" = true" in script


def test_github_ci_exists_before_production_cd() -> None:
    ci = read(CI_WORKFLOW)
    cd = read(CD_WORKFLOW)
    assert "name: CI" in ci
    assert "push:" in ci
    assert "branches:" in ci
    assert "- main" in ci
    assert "name: Production Deploy" in cd
    assert "workflow_run:" in cd
    assert "- CI" in cd
    assert "github.event.workflow_run.conclusion == 'success'" in cd
    assert "concurrency:" in cd
    assert "group: production-deploy" in cd
    assert "cancel-in-progress: false" in cd


def test_production_cd_uses_pinned_host_key_and_minimum_permissions() -> None:
    cd = read(CD_WORKFLOW)
    assert "permissions:" in cd
    assert "contents: read" in cd
    assert "SE_MENTOR_DEPLOY_HOST" in cd
    assert "SE_MENTOR_DEPLOY_USER" in cd
    assert "SE_MENTOR_DEPLOY_SSH_KEY" in cd
    assert "SE_MENTOR_DEPLOY_KNOWN_HOSTS" in cd
    assert "StrictHostKeyChecking=no" not in cd
    assert "StrictHostKeyChecking=yes" in cd
    assert re.search(r"(?m)^\s*run:\s*env\s*$", cd) is None


def test_production_cd_runbook_documents_host_side_contract() -> None:
    runbook = read(RUNBOOK)
    assert "/etc/se-mentor/production.env" in runbook
    assert "SE_MENTOR_RUNTIME_PROFILE=ONLINE_SAFE" in runbook
    assert "SE_MENTOR_TRUST_PROXY=true" in runbook
    assert "SE_MENTOR_TLS_CERT_DIR=/etc/se-mentor/tls" in runbook
    assert "SE_MENTOR_ACME_WEBROOT=/var/lib/se-mentor/acme-webroot" in runbook
    assert "SE_MENTOR_DEPLOY_KNOWN_HOSTS" in runbook
    assert "Do not paste the private key into Codex" in runbook
