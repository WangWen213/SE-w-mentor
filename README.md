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
