from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_T107_docker_files_exist() -> None:
    assert (ROOT / "backend" / "Dockerfile").is_file()
    assert (ROOT / "backend" / "docker-entrypoint.sh").is_file()
    assert (ROOT / "frontend" / "Dockerfile").is_file()
    assert (ROOT / "deploy" / "docker-compose.yml").is_file()
    assert (ROOT / "deploy" / "scripts" / "smoke_compose.sh").is_file()
    assert (ROOT / ".dockerignore").is_file()


def test_T107_backend_image_is_multistage_non_root_and_uses_project_python() -> None:
    dockerfile = read("backend/Dockerfile")
    assert "FROM python:3.13-slim AS builder" in dockerfile
    assert "FROM python:3.13-slim AS runtime" in dockerfile
    assert "python -m pip wheel" in dockerfile
    assert "USER sementor" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "backend/.venv" not in dockerfile
    assert "python:latest" not in dockerfile

    entrypoint = read("backend/docker-entrypoint.sh")
    assert "alembic -c /app/alembic.ini" in entrypoint
    assert "upgrade head" in entrypoint
    assert "uvicorn se_mentor.main:create_app" in entrypoint
    assert "SE_MENTOR_RUNTIME_PROFILE=CLOUD_DEMO" in entrypoint


def test_T107_frontend_image_is_multistage_and_static_only() -> None:
    dockerfile = read("frontend/Dockerfile")
    assert "FROM node:20-bookworm AS builder" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime" in dockerfile
    assert "COPY --from=builder /app/dist" in dockerfile
    assert "npm run dev" not in dockerfile
    assert "node_modules" not in dockerfile
    assert "node:latest" not in dockerfile


def test_T107_compose_enforces_cloud_demo_persistence_and_local_backend_boundary() -> (
    None
):
    compose = read("deploy/docker-compose.yml")
    assert "SE_MENTOR_RUNTIME_PROFILE: CLOUD_DEMO" in compose
    assert "SE_MENTOR_DEMO_WORKSPACE: /var/lib/se-mentor/demo-workspace" in compose
    assert (
        "SE_MENTOR_DATABASE_URL: sqlite:////var/lib/se-mentor/se_mentor_api.sqlite3"
        in compose
    )
    assert "se_mentor_runtime:/var/lib/se-mentor" in compose
    assert "condition: service_healthy" in compose
    assert "127.0.0.1" in compose
    assert re.search(r'"127\.0\.0\.1:\$\{SE_MENTOR_BACKEND_PORT:-8000\}:8000"', compose)
    assert "8000:8000" not in compose
    assert "OPENAI_API_KEY" not in compose
    assert "SE_MENTOR_OPENAI_API_KEY" not in compose
    assert "${PROJECT_PATH}" not in compose
    assert ":/workspace" not in compose


def test_T108_compose_gateway_is_the_public_entrypoint() -> None:
    compose = read("deploy/docker-compose.yml")
    assert "  gateway:" in compose
    assert "./nginx/se-mentor.conf:/etc/nginx/conf.d/default.conf:ro" in compose
    assert (
        "./nginx/snippets/se-mentor-locations.conf:/etc/nginx/se-mentor-locations.conf:ro"
        in compose
    )
    assert '"127.0.0.1:${SE_MENTOR_GATEWAY_HTTP_PORT:-8088}:8080"' in compose
    assert "frontend:" in compose
    assert "backend:" in compose
    assert "se_mentor_internal" in compose


def test_T109_production_compose_publishes_only_gateway_http() -> None:
    assert (ROOT / "deploy" / "docker-compose.production.yml").is_file()

    command = [
        "docker",
        "compose",
        "-f",
        "deploy/docker-compose.yml",
        "-f",
        "deploy/docker-compose.production.yml",
        "config",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("docker compose CLI is not available")

    assert completed.returncode == 0, completed.stderr
    config = json.loads(completed.stdout)
    services = config["services"]

    assert services["backend"].get("ports", []) == []
    assert services["frontend"].get("ports", []) == []

    gateway_ports = services["gateway"]["ports"]
    assert gateway_ports == [
        {
            "mode": "ingress",
            "target": 8080,
            "published": "80",
            "protocol": "tcp",
        }
    ]
    assert "se_mentor_runtime" in config["volumes"]
    assert "se_mentor_internal" in config["networks"]
    assert services["backend"]["environment"]["SE_MENTOR_RUNTIME_PROFILE"] == "CLOUD_DEMO"
    assert "47.76.106.57" not in read("deploy/docker-compose.production.yml")


def test_T107_dockerignore_excludes_dev_runtime_and_secret_material() -> None:
    dockerignore = read(".dockerignore")
    for pattern in (
        ".git",
        "backend/.venv/",
        "frontend/node_modules/",
        "packaging/dist/",
        "deploy/.sementor/",
        ".env",
        "*.pem",
        "*.key",
        "*.sqlite3",
        "perf-result.txt",
    ):
        assert pattern in dockerignore


def test_T107_smoke_script_is_fail_closed_and_checks_recreate_persistence() -> None:
    smoke = read("deploy/scripts/smoke_compose.sh")
    assert "set -Eeuo pipefail" in smoke
    assert "docker compose" in smoke
    assert "compose config" in smoke
    assert "compose build" in smoke
    assert "compose up -d" in smoke
    assert "curl -fsS" in smoke
    assert "compose rm -sf backend" in smoke
    assert "t107-persistence-marker" in smoke
    assert "down -v" not in smoke
    assert "|| true" not in smoke
