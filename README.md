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

## Deterministic Harness Mechanism Demo

The coursework mechanism demo is an offline CLI artifact, separate from the Online WebUI,
ONLINE_SAFE profile, ECS deployment, and public URL.

It uses the real harness path with `MockLLMProvider`: context building, action parsing,
governance decisioning, dispatcher gating, validation feedback, and engineering-memory retrieval.
It does not require a real LLM, API key, network, Credential Manager, ECS, or a user project.
Each run creates an isolated temporary fixture repository and temporary SQLite state.

Main command:

```powershell
$env:PYTHONPATH=(Resolve-Path backend\src).Path
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --all
```

Scenario commands:

```powershell
$env:PYTHONPATH=(Resolve-Path backend\src).Path
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario governance
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario feedback
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --scenario memory
.\backend\.venv\Scripts\python.exe scripts\demo_harness.py --all --output $env:TEMP\sementor-demo-evidence
```

Expected summary:

```text
Governance Guardrail             PASS
Feedback-driven Self Correction  PASS
Engineering Memory / Context     PASS

Scenarios passed: 3 / 3
```
