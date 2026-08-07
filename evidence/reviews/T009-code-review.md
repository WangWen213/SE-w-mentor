# T009 Code Review

Status: PASS.

## P1

None.

## P2

None.

## P3

None.

## P4

- Existing third-party `StarletteDeprecationWarning` remains outside T009.

## Credential Persistence Safety

No credential plaintext at rest:

- SQLAlchemy columns exclude `secret`, `api_key`, `token`, `password`, and `credential_value`.
- Migration columns exclude those sinks.
- `CredentialProfile` rejects forbidden constructor keywords and attribute assignment.
- Tests verify the migration text and SQLite dump do not contain `fake-secret-T009` or forbidden
  plaintext field names.

## Review Notes

- DB integrity: PKs, FKs, unique constraints, project-path uniqueness, project config version
  uniqueness, child indexes, and cascade behavior are covered.
- Normalization: deterministic path normalization uses absolute/non-strict path normalization and
  Windows normcase where applicable; it does not require path existence.
- Migration reversibility: upgrade/downgrade/re-upgrade passed on an isolated SQLite DB.
- Import side effects: Alembic imports `se_mentor.models` only to register metadata for migrations.
- Scope creep: no T010 task/proposal/iteration model or migration exists.
