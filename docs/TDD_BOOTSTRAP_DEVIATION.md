# TDD Bootstrap Deviation

This document records the known deviation from strict TDD during initial scaffold preparation.

## Summary

T002, T003, T007, and T008 were partially implemented before their PLAN-specified red tests and
full evidence packets existed. This was done to prepare the repository, dependency environment,
and database baseline. The deviation is not a precedent for later tasks.

## Rules For Backfill

- Do not delete, revert, or rebuild the existing scaffold solely to manufacture red tests.
- Do not fake red evidence.
- If a PLAN-specified test is now already green, record `PRE_EXISTING_GREEN`.
- If a test still fails, record real red evidence and keep the Task `[-]`.
- Complete strict DoD before marking any Task `[x]`.

## Affected Tasks

| Task | Deviation | Current Evidence Treatment |
| --- | --- | --- |
| T002 | Minimal app scaffold existed before formal red test packet | `PRE_EXISTING_GREEN` for current scaffold smoke tests |
| T003 | Quality command script existed before failure-propagation test | External ordinary non-admin PowerShell canonical gate passed; Codex sandbox Vitest/esbuild native-child failure is classified as `CODEX_SANDBOX_NATIVE_CHILD_RESTRICTION`, not a repository defect |
| T007 | Database base/session and Alembic baseline existed before formal red test packet | `PRE_EXISTING_GREEN` for transaction and FK baseline test |
| T008 | Migration policy and single-head script existed before double-head fixture test | `PRE_EXISTING_GREEN` for the current single-head baseline; real RED covered dual-head fixture, zero-head fixture, policy gaps, and canonical gate wiring |
