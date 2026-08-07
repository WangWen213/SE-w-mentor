# T011 Code Review

Status: PASS.

## P1

None.

## P2

None.

## P3

None.

## P4

- Existing third-party `StarletteDeprecationWarning` remains outside T011.
- Alembic config emits an existing `path_separator` deprecation warning when invoked from the
  in-test migrated DB parity check.
- In-sandbox Vitest/esbuild cannot read `../../..` while loading the frontend config. Earlier
  `check_all.py` gates passed before this documented sandbox restriction.

## Review Notes

- Credential leakage: no secret/plain credential columns exist in `llm_calls` or `agent_actions`;
  unsafe field names are rejected and the sentinel DB dump test passes.
- Prompt/response persistence: no raw prompt, raw response, conversation, raw arguments, or full
  payload fields exist; summaries are bounded strings.
- DB integrity: FK, enum, non-negative numeric, positive action sequence, idempotency, and sequence
  uniqueness constraints are covered.
- Migration graph: `0030_llm_action` follows `0020_task_domain` with exactly one head.
- ORM/migration parity: tests inspect both `Base.metadata.create_all()` and a fresh Alembic-upgraded
  DB.
- Scope creep: no governance, approval, policy, dispatch, provider abstraction, or T012 model was
  introduced.
