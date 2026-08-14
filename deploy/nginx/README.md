# SE-Mentor Gateway

T108 adds a gateway Nginx layer in front of the existing T107 `frontend` and `backend` services. The gateway is the future public entrypoint; the application services stay on the internal Docker network.

## Routing

- `/` proxies to the frontend static service at `frontend:8080`.
- `/api/` proxies to FastAPI at `backend:8000`.
- `/health` proxies to the backend health endpoint.
- `GET /api/tasks/{task_id}/events` is the current task progress event-stream endpoint and has dedicated buffering and timeout settings.

The frontend already uses same-origin `/api/...` requests, so browsers never need to resolve Docker service names such as `backend`.

## SSE

The real progress endpoint is `GET /api/tasks/{task_id}/events`. The gateway disables `proxy_buffering` and `proxy_cache` only for that path pattern and uses longer read/send timeouts so agent progress is not accumulated and released as one delayed response.

## HTTPS Preparation

The committed default config supports HTTP local validation without certificates. The production
override mounts `se-mentor-https.template.conf`, publishes host `80` and `443`, and keeps the
backend/frontend service ports internal. Production HTTPS should mount certificate files from
outside Git, for example:

- `/etc/nginx/certs/fullchain.pem`
- `/etc/nginx/certs/privkey.pem`

The HTTP server serves `/.well-known/acme-challenge/` from `/var/www/acme` before redirecting
other requests to HTTPS. The ACME webroot is a host-managed mount and must not live inside a user
session workspace.

Do not commit certificates, private keys, ACME state, real domains, or public IPs. Phase 5B is
responsible for certificate acquisition, opening `443`, and switching `SE_MENTOR_RUNTIME_PROFILE`
to `ONLINE_SAFE`.

## Trusted Proxy

Nginx overwrites forwarded scheme with `$scheme`:

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

The backend trusts this header only when `SE_MENTOR_TRUST_PROXY=true`. The default is `false`, so
forged direct-client `X-Forwarded-Proto: https` remains insecure.

## Public Boundary

Future cloud security group exposure should be limited to HTTP/HTTPS ingress, plus SSH if needed for administration. FastAPI port `8000` and frontend service port `8080` are internal service ports, not production public entrypoints.
