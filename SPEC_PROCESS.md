# SE-Mentor Spec Process

This process document records how implementation work must relate to the SPEC and PLAN.

## State Sources

- `SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md` records strict Task DoD only.
- `PREP_STATUS.md` records scaffold and local environment readiness.
- `docs/TRACEABILITY_MATRIX.md` records requirement-to-task-to-test evidence mapping.

## DoD Gate

A Task may move to `[x]` only after:

1. Red test evidence exists, or bootstrap `PRE_EXISTING_GREEN` is explicitly accepted.
2. Implementation is green.
3. Related regression commands pass.
4. Spec Review exists.
5. Code Review exists.
6. Evidence files are written.
7. Commit hash is recorded.
8. Working tree is clean.

## Development Pause

T009 and later feature development is paused until T000-T008 are closed under strict DoD.
