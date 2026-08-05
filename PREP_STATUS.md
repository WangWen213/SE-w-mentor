# SE-Mentor Prep Status

This file records engineering environment and scaffold readiness only. Strict task DoD status
remains in `SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md`.

## Naming

- Product: `SE-Mentor`
- Python package: `se_mentor`
- Repository, CLI, and Docker service: `se-mentor`
- Deprecated spelling: `sementor`

## Current Readiness

| Area | Status | Evidence |
| --- | --- | --- |
| Backend Python | Ready | Python 3.13.12, editable install in `backend/.venv` |
| Backend scaffold | Ready | FastAPI `create_app()`, `/health` smoke test |
| Database baseline | Ready for bootstrap | SQLAlchemy base/session, Alembic empty baseline, current single head |
| Frontend scaffold | Ready | React + TypeScript strict + Vite build |
| Frontend tests | Blocked for ordinary sandbox run | Vitest passes only when path permissions allow esbuild to read project config |
| Runtime artifacts | Ignored | `.venv/`, `node_modules/`, `dist/`, `.sementor/`, `.tmp/` |
| T009+ feature work | Paused | Await T000-T008 strict DoD closure |

## Verified Commands

- `backend/.venv/Scripts/python.exe -m ruff format --check .`
- `backend/.venv/Scripts/python.exe -m ruff check .`
- `backend/.venv/Scripts/python.exe -m mypy src tests`
- `backend/.venv/Scripts/python.exe -m pytest`
- `backend/.venv/Scripts/python.exe -m alembic upgrade head`
- `backend/.venv/Scripts/python.exe -m alembic downgrade base`
- `backend/.venv/Scripts/python.exe scripts/check_alembic_heads.py`
- `npm.cmd run type-check`
- `npm.cmd run build`

## Known Blockers

- `npm.cmd run test -- --run` fails under ordinary sandbox permissions with esbuild attempting
  to read `../../..`; T003 remains `[-]` until ordinary-permission Vitest evidence is green.
- T002/T003/T007/T008 were bootstrapped before strict red-green evidence existed; see
  `docs/TDD_BOOTSTRAP_DEVIATION.md`.
