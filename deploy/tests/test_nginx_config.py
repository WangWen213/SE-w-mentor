from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "deploy" / "nginx" / "se-mentor.conf"
SNIPPET = ROOT / "deploy" / "nginx" / "snippets" / "se-mentor-locations.conf"
COMPOSE = ROOT / "deploy" / "docker-compose.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def location_block(config: str, selector: str) -> str:
    marker = f"location {selector} {{"
    start = config.find(marker)
    assert start >= 0, f"missing location {selector}"
    body_start = start + len(marker)
    depth = 1
    index = body_start
    while index < len(config):
        char = config[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return config[body_start:index]
        index += 1
    raise AssertionError(f"unterminated location {selector}")


def test_T108_gateway_config_files_exist() -> None:
    assert NGINX.is_file()
    assert (ROOT / "deploy" / "nginx" / "README.md").is_file()
    assert (ROOT / "deploy" / "nginx" / "se-mentor-https.template.conf").is_file()
    assert SNIPPET.is_file()


def test_T108_frontend_api_health_and_spa_routes_are_defined() -> None:
    config = read(NGINX)
    snippet = read(SNIPPET)
    assert "upstream se_mentor_frontend" in config
    assert "server frontend:8080;" in config
    assert "upstream se_mentor_backend" in config
    assert "server backend:8000;" in config
    assert "include /etc/nginx/se-mentor-locations.conf;" in config

    root = location_block(snippet, "/")
    assert "proxy_pass http://se_mentor_frontend;" in root
    assert "proxy_intercept_errors on;" in root
    assert "error_page 404 =200 /index.html;" in root

    api = location_block(snippet, "/api/")
    assert "proxy_pass http://se_mentor_backend;" in api
    assert "proxy_read_timeout 240s;" in api

    health = location_block(snippet, "= /health")
    assert "proxy_pass http://se_mentor_backend/health;" in health


def test_T108_sse_location_is_specific_and_disables_buffering() -> None:
    config = read(SNIPPET)
    sse_selector = r"~ ^/api/tasks/[^/]+/events$"
    sse = location_block(config, sse_selector)
    assert "proxy_pass http://se_mentor_backend;" in sse
    assert "proxy_buffering off;" in sse
    assert "proxy_cache off;" in sse
    assert "proxy_http_version 1.1;" in sse
    assert "proxy_read_timeout 30m;" in sse
    assert "proxy_send_timeout 30m;" in sse
    assert 'proxy_set_header Accept-Encoding "";' in sse

    api = location_block(config, "/api/")
    assert "proxy_buffering off;" not in api
    assert "proxy_read_timeout 30m;" not in api


def test_T108_security_headers_and_tokens_are_set_without_overstrict_csp_or_hsts() -> (
    None
):
    config = read(NGINX) + read(SNIPPET)
    assert "server_tokens off;" in read(NGINX)
    assert 'add_header X-Content-Type-Options "nosniff" always;' in config
    assert (
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;' in config
    )
    assert 'add_header X-Frame-Options "DENY" always;' in config
    assert (
        'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;'
        in config
    )
    assert "Content-Security-Policy" not in config
    assert "Strict-Transport-Security" not in config
    assert "proxy_set_header Upgrade" not in config
    assert "Connection upgrade" not in config


def test_T108_compose_adds_gateway_without_making_backend_or_frontend_public() -> None:
    compose = read(COMPOSE)
    assert re.search(r"(?m)^  gateway:", compose)
    assert "nginxinc/nginx-unprivileged:1.27-alpine" in compose
    assert "./nginx/se-mentor.conf:/etc/nginx/conf.d/default.conf:ro" in compose
    assert (
        "./nginx/snippets/se-mentor-locations.conf:/etc/nginx/se-mentor-locations.conf:ro"
        in compose
    )
    assert '"127.0.0.1:${SE_MENTOR_GATEWAY_HTTP_PORT:-8088}:8080"' in compose
    assert '"127.0.0.1:${SE_MENTOR_BACKEND_PORT:-8000}:8000"' in compose
    assert '"127.0.0.1:${SE_MENTOR_FRONTEND_PORT:-8080}:8080"' in compose
    assert "8000:8000" not in compose
    assert "8080:8080" not in compose
    assert "condition: service_healthy" in compose


def test_T108_https_is_external_cert_ready_without_committed_material() -> None:
    template = read(ROOT / "deploy" / "nginx" / "se-mentor-https.template.conf")
    assert "ssl_certificate /etc/nginx/certs/fullchain.pem;" in template
    assert "ssl_certificate_key /etc/nginx/certs/privkey.pem;" in template
    assert "return 301 https://$host$request_uri;" in template
    assert "-----BEGIN" not in template

    ignore = read(ROOT / ".gitignore") + read(ROOT / ".dockerignore")
    for pattern in ("*.pem", "*.key", "certs/", "letsencrypt/"):
        assert pattern in ignore
