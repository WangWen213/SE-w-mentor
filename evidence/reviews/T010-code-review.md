# T010 Code Review

Status: PASS.

## P1

None.

## P2

None.

## P3

None.

## P4

- Existing third-party `StarletteDeprecationWarning` remains outside T010.
- In-sandbox Vitest/esbuild cannot read `../../..` while loading the frontend config. Earlier
  `check_all.py` gates passed before this documented sandbox restriction.

## Review Notes

- DB integrity: project/task/proposal/iteration FKs, positive version/iteration checks,
  non-negative task counters, enum checks, and uniqueness indexes are covered by tests.
- Migration parity: tests verify table creation, critical indexes, check constraints, and revision
  lineage in `0020_task_domain`.
- Audit/history behavior: task children do not use arbitrary ORM delete-orphan cascade.
- T009 regression: credential tests were narrowed to avoid false positives from the legitimate
  T010 column `context_token_count`; fake credential values still must not reach the DB dump and
  credential plaintext sink columns remain forbidden.
- Scope creep: no service, API, LLM, or workflow layer was introduced.
