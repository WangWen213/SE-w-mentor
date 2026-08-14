# SE-w-mentor
A project-aware AI software engineering agent with long-term memory and risk-aware code modification support.

## Current Scaffold

This repository is prepared as a monorepo:

- `backend/`: Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic.
- `frontend/`: React, TypeScript strict, Vite.
- `scripts/`: local quality and migration guard entry points.
- `evidence/`: tracked placeholder directories for later task evidence.

The SQLite database is runtime state and must stay out of Git. By default, local state belongs
under `.sementor/`.

## Planned Commands

After installing dependencies:

```bash
cd backend && python -m uvicorn se_mentor.main:create_app --factory
cd backend && python -m alembic upgrade head
cd frontend && npm run dev
```

## Quality Gate

Canonical local quality gate on Windows:

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_all.py
```

Run it from the repository root. The script uses the current Python interpreter for Python checks
and runs frontend commands from `frontend/` with `npm.cmd` on Windows.

`npm.cmd run build` is separate frontend readiness evidence; it is not part of the canonical
`scripts/check_all.py` quality gate.

## Runtime Profiles

- `LOCAL_FULL`: local desktop use. The user opens a local Git repository with "打开本地仓库".
- `CLOUD_DEMO`: public demo mode. It uses the fixed demo workspace and built-in Mock provider;
  no API key is required or accepted.
- `ONLINE_SAFE`: public service mode. The user enters their own OpenAI-compatible credential,
  uploads a project ZIP, SE-Mentor extracts it into a per-session isolated server workspace,
  runs the real Harness, and lets the user download a modified ZIP or patch.

ONLINE_SAFE does not access the user's local filesystem directly and does not use a local bridge.
See `docs/ONLINE_SAFE_PHASE5A_READINESS.md` for HTTPS/trusted-proxy and manual Web E2E readiness.
