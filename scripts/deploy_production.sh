#!/usr/bin/env sh
set -eu

REPO_DIR="${SE_MENTOR_REPO_DIR:-/opt/se-mentor}"
ENV_FILE="${SE_MENTOR_PRODUCTION_ENV_FILE:-/etc/se-mentor/production.env}"
HEALTH_URL="${SE_MENTOR_PRODUCTION_HEALTH_URL:-https://47.76.106.57/health}"
STATUS_URL="${SE_MENTOR_PRODUCTION_STATUS_URL:-https://47.76.106.57/api/credentials/llm/status}"
COMPOSE_FILE="deploy/docker-compose.yml"
PRODUCTION_COMPOSE_FILE="deploy/docker-compose.production.yml"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is missing: $1"
}

compose() {
  docker compose -f "$COMPOSE_FILE" -f "$PRODUCTION_COMPOSE_FILE" "$@"
}

require_clean_tracked_tree() {
  git diff --quiet -- || fail "tracked working tree has unstaged changes"
  git diff --cached --quiet -- || fail "tracked working tree has staged changes"
}

load_production_env() {
  [ -f "$ENV_FILE" ] || fail "production env file is missing: $ENV_FILE"
  [ -r "$ENV_FILE" ] || fail "production env file is not readable: $ENV_FILE"

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "" | \#*) continue ;;
      *=*) ;;
      *) fail "invalid production env line; expected KEY=value" ;;
    esac

    key=${line%%=*}
    value=${line#*=}
    case "$key" in
      SE_MENTOR_RUNTIME_PROFILE | SE_MENTOR_TRUST_PROXY | SE_MENTOR_TLS_CERT_DIR | SE_MENTOR_ACME_WEBROOT)
        export "$key=$value"
        ;;
      *)
        fail "unsupported production env key: $key"
        ;;
    esac
  done <"$ENV_FILE"
}

validate_production_env() {
  [ "${SE_MENTOR_RUNTIME_PROFILE:-}" = "ONLINE_SAFE" ] || fail "SE_MENTOR_RUNTIME_PROFILE must be ONLINE_SAFE"
  [ "${SE_MENTOR_TRUST_PROXY:-}" = "true" ] || fail "SE_MENTOR_TRUST_PROXY must be true"
  [ -d "${SE_MENTOR_TLS_CERT_DIR:-}" ] || fail "SE_MENTOR_TLS_CERT_DIR does not exist"
  [ -d "${SE_MENTOR_ACME_WEBROOT:-}" ] || fail "SE_MENTOR_ACME_WEBROOT does not exist"
  [ -f "${SE_MENTOR_TLS_CERT_DIR}/fullchain.pem" ] || fail "TLS fullchain.pem is missing"
  [ -f "${SE_MENTOR_TLS_CERT_DIR}/privkey.pem" ] || fail "TLS privkey.pem is missing"
}

wait_for_backend_health() {
  deadline=$(($(date +%s) + 90))
  while [ "$(date +%s)" -le "$deadline" ]; do
    backend_id=$(compose ps -q backend)
    [ -n "$backend_id" ] || fail "backend container is not present"
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$backend_id" 2>/dev/null || true)
    if [ "$health" = "healthy" ]; then
      log "backend health check passed"
      return 0
    fi
    sleep 3
  done
  compose ps
  fail "backend did not become healthy within 90 seconds"
}

wait_for_gateway_health() {
  response_file="${TMPDIR:-/tmp}/se-mentor-health.$$"
  trap 'rm -f "$response_file"' EXIT HUP INT TERM
  deadline=$(($(date +%s) + 90))
  while [ "$(date +%s)" -le "$deadline" ]; do
    if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >"$response_file"; then
      if grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$response_file"; then
        log "gateway health check passed"
        return 0
      fi
    fi
    sleep 3
  done
  fail "gateway health check failed within 90 seconds"
}

verify_runtime_environment() {
  backend_id=$(compose ps -q backend)
  [ -n "$backend_id" ] || fail "backend container is not present"
  docker exec "$backend_id" sh -c '[ "$SE_MENTOR_RUNTIME_PROFILE" = ONLINE_SAFE ] && [ "$SE_MENTOR_TRUST_PROXY" = true ]' \
    || fail "backend PID 1 runtime environment is not ONLINE_SAFE/trusted-proxy"
}

verify_credential_status() {
  response_file="${TMPDIR:-/tmp}/se-mentor-credentials.$$"
  trap 'rm -f "$response_file"' EXIT HUP INT TERM
  curl --fail --silent --show-error --max-time 10 "$STATUS_URL" >"$response_file" \
    || fail "credential status endpoint request failed"
  grep -Eq '"profile"[[:space:]]*:[[:space:]]*"ONLINE_SAFE"' "$response_file" \
    || fail "credential status did not report ONLINE_SAFE profile"
  grep -Eq '"source"[[:space:]]*:[[:space:]]*"(ONLINE_SAFE|ONLINE_SAFE_SESSION)"' "$response_file" \
    || fail "credential status did not report ONLINE_SAFE source"
  grep -Eq '"provider"[[:space:]]*:[[:space:]]*"OpenAI"' "$response_file" \
    || fail "credential status did not report OpenAI provider"
  if grep -Eq '"source"[[:space:]]*:[[:space:]]*"CLOUD_DEMO"|"provider"[[:space:]]*:[[:space:]]*"Mock"' "$response_file"; then
    fail "credential status reported CLOUD_DEMO/Mock"
  fi
}

require_command git
require_command docker
require_command curl

cd "$REPO_DIR"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || fail "production checkout must be on main"
require_clean_tracked_tree

log "fetching origin/main"
git fetch origin main
require_clean_tracked_tree
git merge --ff-only origin/main

load_production_env
validate_production_env
compose config >/dev/null

log "building production backend/frontend images"
compose build backend frontend

log "recreating production services"
compose up -d --no-build backend frontend gateway
compose ps

wait_for_backend_health
wait_for_gateway_health
verify_runtime_environment
verify_credential_status

log "production deployment passed"
