# T114 First Cold-Start Validation

Status: PASS

Date: 2026-08-07

Reviewer inputs:

- Main agent local cold-start reread of Foundation/M0 docs and Git state.
- Fresh read-only subagent `019fdb15-ea18-7701-83f1-883f6d7757c0`.

## Required PASS Assertions

- T000-T008 complete: PASS. The PLAN marks T000 through T008 `[x]`, and git-visible evidence
  exists for T000-T008 JUnit, TDD notes, reviews, diffs, and AGENT_LOG entries.
- decision freeze coherent: PASS. `docs/DECISIONS_P0.md` freezes OQ-01 through OQ-20 and now
  states that T009+ remains paused until T114 first cold-start PASS.
- traceability coherent: PASS. `scripts/check_traceability.py` reports 134 P0 requirements mapped,
  and `docs/TRACEABILITY_MATRIX.md` includes the verified T008 governance row.
- shared contracts coherent: PASS. T004 contract files, schema snapshots, and reviews remain
  referenced by PLAN and evidence.
- migration ownership coherent: PASS. `docs/MIGRATION_POLICY.md` defines `wt-schema` ownership,
  revision allocation, conflict handling, and fail-closed CI behavior.
- single Alembic head: PASS. `scripts/check_alembic_heads.py` and `alembic heads` both report
  `0001_initial_baseline` as the only head.
- canonical check clear: PASS WITH ENVIRONMENT NOTE. README names
  `.\backend\.venv\Scripts\python.exe scripts\check_all.py`; `PREP_STATUS.md` records that
  frontend Vitest full canonical evidence must be produced in ordinary external PowerShell because
  Codex sandbox native-child Vitest loading is a documented environment restriction.
- T009 NOT STARTED: PASS. No tracked `backend/src/se_mentor/models/project.py`,
  `0010_project_domain.py`, or T009 test/evidence implementation exists; PLAN keeps T009 `[ ]`.

## Fresh-Agent Findings And Fixes

The fresh-agent review initially returned BLOCKED due to documentation drift, not product code:

- `docs/TDD_BOOTSTRAP_DEVIATION.md` still described T003/T008 as unresolved.
- T009 gating was inconsistent because some docs stopped at T000-T008 and did not mention T114.
- `npm run build` needed to be clarified as readiness evidence rather than part of `check_all.py`.
- `docs/TRACEABILITY_MATRIX.md` still called itself a T001 strict DoD candidate.

Fixes applied in this pass:

- Updated `docs/TDD_BOOTSTRAP_DEVIATION.md` for final T003 and T008 evidence handling.
- Updated `SPEC_PROCESS.md`, `docs/DECISIONS_P0.md`, and `PREP_STATUS.md` to state that T009+
  waits for T000-T008 strict DoD plus T114 first cold-start PASS.
- Clarified `npm.cmd run build` in `README.md` and `PREP_STATUS.md`.
- Updated the traceability matrix status line to frozen/current.

## Conclusion

Foundation/M0 first cold-start pass is PASS after the documentation fixes above. T009 NOT STARTED.
