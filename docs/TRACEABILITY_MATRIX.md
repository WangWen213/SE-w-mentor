# Traceability Matrix

Status: bootstrap draft. This file freezes the columns and initial P0 entries; it is not yet a
complete release matrix.

| requirement | priority | task | test | evidence | status |
| --- | --- | --- | --- | --- | --- |
| P0 decisions and bootstrap exception | P0 | T000 | `tests/meta/test_t000_decisions.py` | `evidence/tdd/T000.md`; `evidence/test-reports/T000.xml`; `evidence/reviews/T000-spec-review.md`; `evidence/reviews/T000-code-review.md` | complete |
| Evidence format and traceability columns | P0 | T001 | `tests/meta/test_traceability.py` | `evidence/tdd/T001.md` | draft |
| Minimal backend and frontend scaffold | P0 | T002 | `backend/tests/test_scaffold.py`; `frontend/src/smoke.test.ts` | `evidence/tdd/T002.md` | in_progress |
| Quality command entry points | P0 | T003 | `scripts/check_all.py`; frontend ordinary permission run | `evidence/tdd/T003.md` | blocked |
| Shared contract naming and model placement | P0 | T004 | pending | `evidence/tdd/T004.md` | not_started |
| Layered config and profiles | P0 | T005 | pending | `evidence/tdd/T005.md` | not_started |
| SQLite, SQLAlchemy, Alembic baseline | P0 | T007 | `backend/tests/db/test_session.py` | `evidence/tdd/T007.md` | in_progress |
| Migration ownership and single head | P0 | T008 | `scripts/check_alembic_heads.py` | `evidence/tdd/T008.md` | in_progress |
