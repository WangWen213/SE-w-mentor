FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src

RUN python -m pip wheel --wheel-dir /wheelhouse ./backend

FROM python:3.13-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SE_MENTOR_HOST=0.0.0.0 \
    SE_MENTOR_PORT=8000 \
    SE_MENTOR_RUNTIME_PROFILE=CLOUD_DEMO \
    SE_MENTOR_RUNTIME_ROOT=/var/lib/se-mentor \
    SE_MENTOR_DEMO_RUNTIME_ROOT=/var/lib/se-mentor \
    SE_MENTOR_DEMO_WORKSPACE=/var/lib/se-mentor/demo-workspace \
    SE_MENTOR_DATABASE_URL=sqlite:////var/lib/se-mentor/se_mentor_api.sqlite3

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /home/sementor --shell /usr/sbin/nologin sementor \
    && mkdir -p /app /opt/se-mentor /var/lib/se-mentor /tmp/se-mentor \
    && chown -R sementor:sementor /app /opt/se-mentor /var/lib/se-mentor /tmp/se-mentor

WORKDIR /app

COPY --from=builder /wheelhouse /wheelhouse
RUN python -m pip install --no-index --find-links=/wheelhouse se-mentor \
    && rm -rf /wheelhouse

COPY backend/alembic.ini /app/alembic.ini
COPY backend/migrations /app/migrations
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh
COPY deploy/demo-workspace /opt/se-mentor/demo-workspace

RUN chown -R sementor:sementor /app /opt/se-mentor /var/lib/se-mentor \
    && chmod 0755 /app/docker-entrypoint.sh

USER sementor

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2).read()"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
