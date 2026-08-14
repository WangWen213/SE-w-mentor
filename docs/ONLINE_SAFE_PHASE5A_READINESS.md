# ONLINE_SAFE Phase 5A Readiness

Phase 5A prepares the repository for an HTTPS ONLINE_SAFE cutover without deploying it.
The current public ECS deployment must remain `http://47.76.106.57` running `CLOUD_DEMO`
until Phase 5B.

## Runtime Profiles

- `LOCAL_FULL`: opens a local Git repository on the user's computer and keeps the existing
  local credential semantics.
- `CLOUD_DEMO`: uses the fixed demo workspace and built-in `MockLLMProvider`; no user API key
  is needed or accepted.
- `ONLINE_SAFE`: the user enters an OpenAI-compatible credential in the browser, uploads a
  project ZIP, the backend extracts it into the current session's isolated workspace, creates
  a fresh Git baseline, runs the real Harness, and exports a modified ZIP or patch.

ONLINE_SAFE does not access the user's local filesystem directly. It does not use the
Browser File System Access API, a local bridge, or client-local repository synchronization.

## Trusted Proxy And HTTPS

ONLINE_SAFE credential and execution readiness require a secure request. The backend accepts:

- direct `https` requests; or
- `X-Forwarded-Proto: https` only when `SE_MENTOR_TRUST_PROXY=true`.

`SE_MENTOR_TRUST_PROXY` defaults to `false`. Forged `X-Forwarded-Proto` on direct HTTP is
therefore rejected by default. Production Nginx must overwrite forwarded scheme with:

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

Do not use `$http_x_forwarded_proto`.

## HTTPS Gateway Contract

The committed production template keeps the existing gateway Nginx:

- host `:80` maps to gateway `:8080`;
- `/.well-known/acme-challenge/` is served from a host-managed ACME webroot;
- other HTTP requests redirect to HTTPS;
- host `:443` maps to gateway `:8443`;
- TLS certificates are mounted read-only from outside Git;
- `/` proxies to `frontend:8080`;
- `/api/*` proxies to `backend:8000`;
- `GET /api/tasks/{task_id}/events` keeps buffering disabled and long timeouts.

Backend `8000` and frontend `8080` remain internal service ports in production.

## Certificate Material

Do not commit or bake certificate material into images. Phase 5B should mount:

- `${SE_MENTOR_TLS_CERT_DIR}/fullchain.pem` to `/etc/nginx/certs/fullchain.pem`;
- `${SE_MENTOR_TLS_CERT_DIR}/privkey.pem` to `/etc/nginx/certs/privkey.pem`;
- `${SE_MENTOR_ACME_WEBROOT}` to `/var/www/acme`.

The ACME webroot must not be inside any user session workspace and must not be writable by
the Harness.

## ONLINE_SAFE Readiness Policy

The temporary `ONLINE_SAFE_EXECUTION_NOT_READY` API gate is replaced by explicit readiness:

- secure request;
- current ONLINE_SAFE session;
- session credential configured and SSRF-validated;
- current session project ownership;
- project root bound to the current session workspace;
- project bootstrap/index ready for proposal context;
- execution through the existing Harness with ONLINE_SAFE tool restrictions.

RUN_COMMAND remains unavailable as an agent tool in ONLINE_SAFE. The WebUI dispatches the
ONLINE_SAFE execution command label `APPLY_APPROVED_CHANGES`, while the agent runtime exposes
only bounded read/search/write file tools.

## Tool Policy

- `READ_FILE`: allowed inside the session workspace.
- `SEARCH_CODE`: allowed inside the session workspace.
- `APPLY_PATCH`: allowed inside the session workspace under policy.
- `CREATE_FILE`: allowed inside the session workspace under policy.
- `DELETE_FILE`: allowed inside the session workspace under policy.
- `RUN_VALIDATION`: not enabled for ONLINE_SAFE in Phase 5A.
- `RUN_COMMAND`: disabled for ONLINE_SAFE.

## Real Web E2E Acceptance Gate

Automated tests can only prove repository readiness. The final browser acceptance requires
the user to enter their own real OpenAI-compatible API key in the WebUI. Codex must not ask
for, read, log, or commit that key.

Expected flow:

ZIP upload -> Project/bootstrap -> real credential -> Task -> real Proposal -> Confirm ->
Impact -> Governance -> Execution -> real SSE -> actual workspace modification -> completion ->
ZIP export -> verify exported ZIP contains the actual modification.

MockLLMProvider is not accepted for this gate.

## Manual Browser Acceptance Steps

Use the small fixture in `docs/acceptance/online-safe-fixture`.

1. Create `online-safe-fixture.zip` from the fixture directory.
   Expected result: the ZIP contains `app.py` and `README.md`, with no `.git` or secrets.
   Failure evidence: ZIP listing.

2. Start local ONLINE_SAFE behind the HTTPS-capable gateway after Phase 5B-style local setup,
   or use the future Phase 5B production cutover.
   Expected result: browser URL is HTTPS and backend has `SE_MENTOR_TRUST_PROXY=true`.
   Failure evidence: backend logs and `/api/credentials/llm/status` response.

3. In the WebUI, open Settings and enter API Base URL, Model, and API Key yourself.
   Expected result: status shows configured, key is not echoed after refresh.
   Failure evidence: browser network response and backend logs with secrets redacted.

4. Click `上传项目` and select `online-safe-fixture.zip`.
   Expected result: project appears as an online project; no server absolute path is shown.
   Failure evidence: `/api/projects/import-zip` response.

5. Create the task: `把 app.py 中的 TITLE 从 Course Portal 改成 Mentor Portal，并保持其他行为不变。`
   Expected result: task is created for the uploaded project.
   Failure evidence: `/api/tasks` response.

6. Generate a proposal.
   Expected result: real provider proposal references `app.py`; no `ONLINE_SAFE_*_NOT_READY`
   error appears.
   Failure evidence: `/api/tasks/{task_id}/proposals` response.

7. Confirm the proposal and inspect Impact/Governance.
   Expected result: Impact is generated and Governance reaches ALLOW/WARN/BLOCK.
   Failure evidence: governance response and task timeline.

8. If allowed, let Execution run.
   Expected result: real SSE events arrive on `GET /api/tasks/{task_id}/events`; completion is
   visible without refresh; `app.py` is actually modified.
   Failure evidence: event stream, execution response, backend logs.

9. Download the modified project ZIP.
   Expected result: exported ZIP opens locally and `app.py` contains `Mentor Portal`.
   It must not contain `.git`, API keys, session IDs, SQLite runtime DBs, logs, certs, private
   keys, or server absolute path metadata.
   Failure evidence: ZIP listing and extracted file content.

10. Download Patch when applicable.
    Expected result: tracked-only changes produce a patch; if created files are untracked,
    a 409 response tells the user to download the full ZIP.
    Failure evidence: patch response body/status.

## Acceptance Result

REAL WEB E2E ACCEPTANCE = PENDING USER RUNTIME ACCEPTANCE

This must not be changed to PASS until a user manually runs the HTTPS browser flow with a
real provider credential and verifies the exported ZIP.

## Phase 5B Prerequisites

1. Acquire and install the Let's Encrypt IP address certificate outside Git.
2. Mount certificate files and ACME webroot into the gateway.
3. Set `SE_MENTOR_RUNTIME_PROFILE=ONLINE_SAFE`.
4. Set `SE_MENTOR_TRUST_PROXY=true`.
5. Open/allow public `443` only during the controlled cutover.
6. Run the real Web E2E acceptance gate above.
7. Keep `CLOUD_DEMO` available until the cutover is explicitly approved.
