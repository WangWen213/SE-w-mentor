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
| Frontend tests | Ready outside Codex sandbox | User-executed ordinary non-admin PowerShell: Vitest pass, Vite build pass |
| Quality gate | Ready outside Codex sandbox | User-executed ordinary non-admin PowerShell: canonical `check_all.py` pass |
| Runtime artifacts | Ignored | `.venv/`, `node_modules/`, `dist/`, `.sementor/`, `.tmp/`, backups, logs, secrets |
| T009+ feature work | Paused | Await T000-T008 strict DoD closure plus T114 first cold-start PASS |

## Verified Commands

- `backend/.venv/Scripts/python.exe -m ruff format --check .`
- `backend/.venv/Scripts/python.exe -m ruff check .`
- `backend/.venv/Scripts/python.exe -m mypy src tests`
- `backend/.venv/Scripts/python.exe -m pytest`
- `backend/.venv/Scripts/python.exe -m alembic upgrade head`
- `backend/.venv/Scripts/python.exe -m alembic downgrade base`
- `backend/.venv/Scripts/python.exe scripts/check_alembic_heads.py`
- `npm.cmd run type-check`
- `npm.cmd run build` as separate frontend readiness/build evidence, not part of
  `scripts/check_all.py`
- `npm.cmd run test -- --run` in an external ordinary non-admin PowerShell
- `backend/.venv/Scripts/python.exe scripts/check_all.py` passed in an external ordinary non-admin PowerShell

## Known Blockers

- Codex sandbox native child processes can fail Vite/Vitest config loading with
  `Cannot read directory "../../.."`. This is classified as
  `CODEX_SANDBOX_NATIVE_CHILD_RESTRICTION`, not a repository Vitest/Vite defect. Do not modify
  Windows ACLs or restructure Vite/Vitest to accommodate this sandbox limitation.
- Existing third-party dependency warning: `StarletteDeprecationWarning` from FastAPI/Starlette
  TestClient/httpx compatibility. It is not a T003 blocker and should be handled later through
  dependency governance.
- T002/T003/T007/T008 were bootstrapped before strict red-green evidence existed; see
  `docs/TDD_BOOTSTRAP_DEVIATION.md`.
