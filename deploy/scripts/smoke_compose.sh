#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-se-mentor-t107-smoke}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.yml"
BACKEND_PORT="${SE_MENTOR_BACKEND_PORT:-18080}"
FRONTEND_PORT="${SE_MENTOR_FRONTEND_PORT:-18081}"
GATEWAY_PORT="${SE_MENTOR_GATEWAY_HTTP_PORT:-18082}"
RUNTIME_VOLUME="${PROJECT_NAME}_se_mentor_runtime"

cleanup() {
  status=$?
  set +e
  COMPOSE_PROJECT_NAME="${PROJECT_NAME}" \
  SE_MENTOR_BACKEND_PORT="${BACKEND_PORT}" \
  SE_MENTOR_FRONTEND_PORT="${FRONTEND_PORT}" \
  SE_MENTOR_GATEWAY_HTTP_PORT="${GATEWAY_PORT}" \
    docker compose -f "${COMPOSE_FILE}" down --remove-orphans >/dev/null 2>&1
  docker volume rm "${RUNTIME_VOLUME}" >/dev/null 2>&1
  exit "${status}"
}

trap cleanup EXIT INT TERM

compose() {
  COMPOSE_PROJECT_NAME="${PROJECT_NAME}" \
  SE_MENTOR_BACKEND_PORT="${BACKEND_PORT}" \
  SE_MENTOR_FRONTEND_PORT="${FRONTEND_PORT}" \
  SE_MENTOR_GATEWAY_HTTP_PORT="${GATEWAY_PORT}" \
    docker compose -f "${COMPOSE_FILE}" "$@"
}

wait_for_http() {
  url="$1"
  attempts="${2:-60}"
  i=0
  while [ "${i}" -lt "${attempts}" ]; do
    if curl -fsS "${url}" >/dev/null; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "Timed out waiting for ${url}" >&2
  return 1
}

assert_no_secret_files() {
  service="$1"
  compose exec -T "${service}" sh -c \
    "test -z \"\$(find /app /opt/se-mentor -name .env -o -name '.env.*' -o -name '*.pem' -o -name '*.key' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' -o -name 'perf-result.txt' | head -n 1)\""
}

docker version >/dev/null
docker compose version >/dev/null

compose config >/dev/null
compose build
compose up -d

wait_for_http "http://127.0.0.1:${BACKEND_PORT}/health"
wait_for_http "http://127.0.0.1:${FRONTEND_PORT}/"
wait_for_http "http://127.0.0.1:${GATEWAY_PORT}/health"
wait_for_http "http://127.0.0.1:${GATEWAY_PORT}/"

compose exec -T backend sh -c "test -s /var/lib/se-mentor/se_mentor_api.sqlite3"
compose exec -T backend sh -c "printf t107-smoke > /var/lib/se-mentor/t107-persistence-marker"
compose exec -T backend sh -c "test -d /var/lib/se-mentor/demo-workspace/.baseline"

assert_no_secret_files backend
assert_no_secret_files frontend

compose rm -sf backend
compose up -d backend
wait_for_http "http://127.0.0.1:${BACKEND_PORT}/health"
wait_for_http "http://127.0.0.1:${GATEWAY_PORT}/health"

compose exec -T backend sh -c "test -s /var/lib/se-mentor/se_mentor_api.sqlite3"
compose exec -T backend sh -c "test \"\$(cat /var/lib/se-mentor/t107-persistence-marker)\" = t107-smoke"

echo "T107 compose smoke passed."
