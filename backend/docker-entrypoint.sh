#!/usr/bin/env sh
set -eu

: "${SE_MENTOR_RUNTIME_ROOT:=/var/lib/se-mentor}"
: "${SE_MENTOR_DEMO_RUNTIME_ROOT:=${SE_MENTOR_RUNTIME_ROOT}}"
: "${SE_MENTOR_DEMO_WORKSPACE:=${SE_MENTOR_RUNTIME_ROOT}/demo-workspace}"
: "${SE_MENTOR_DATABASE_URL:=sqlite:///${SE_MENTOR_RUNTIME_ROOT}/se_mentor_api.sqlite3}"
: "${SE_MENTOR_HOST:=0.0.0.0}"
: "${SE_MENTOR_PORT:=8000}"
: "${SE_MENTOR_RUNTIME_PROFILE:=CLOUD_DEMO}"

mkdir -p "${SE_MENTOR_RUNTIME_ROOT}" "$(dirname "${SE_MENTOR_DEMO_WORKSPACE}")" /tmp/se-mentor

if [ ! -d "${SE_MENTOR_DEMO_WORKSPACE}/.baseline" ]; then
  rm -rf "${SE_MENTOR_DEMO_WORKSPACE}"
  cp -R /opt/se-mentor/demo-workspace "${SE_MENTOR_DEMO_WORKSPACE}"
fi

export SE_MENTOR_RUNTIME_PROFILE
export SE_MENTOR_RUNTIME_ROOT
export SE_MENTOR_DEMO_RUNTIME_ROOT
export SE_MENTOR_DEMO_WORKSPACE
export SE_MENTOR_DATABASE_URL
export TMPDIR=/tmp/se-mentor

alembic -c /app/alembic.ini -x "database_url=${SE_MENTOR_DATABASE_URL}" upgrade head

exec uvicorn se_mentor.main:create_app --host "${SE_MENTOR_HOST}" --port "${SE_MENTOR_PORT}"
