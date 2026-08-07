# T012 Code Review

Status: PASS.

## P1

None.

## P2

None.

## P3

None.

## P4

- Existing third-party `StarletteDeprecationWarning` remains outside T012.
- Alembic config emits an existing `path_separator` deprecation warning when invoked from the
  in-test migrated DB parity check.
- In-sandbox Vitest/esbuild cannot read `../../..` while loading the frontend config. Earlier
  `check_all.py` gates passed before this documented sandbox restriction.
- A non-sandbox `check_all.py` retry encountered host-level denial deleting
  `.tmp/check-all/*-pytest-basetemp`, also outside T012 code.

## Review Notes

- Secret leakage: no secret, credential, password, token, raw prompt, raw response, conversation,
  source dump, or full log sink columns were added to governance tables.
- DB integrity: FK, enum, non-empty evidence, proposal hash length, rule version positivity,
  priority non-negativity, hard-DENY override, duplicate hit, and rule identity/version constraints
  are covered.
- Exact rule history: hits bind to `(rule_id, rule_version)` and decision history remains attached
  to the original rule version even after a later version exists.
- Migration graph: `0040_governance` follows `0030_llm_action` with exactly one head.
- ORM/migration parity: tests inspect both `Base.metadata.create_all()` and a fresh
  Alembic-upgraded DB.
- Scope creep: no approval, policy, temporary grant, policy evaluator, governance engine,
  execution gate, API, UI, or T013 model was introduced.
