# Evidence Format

T001 freezes the evidence layout used by P0 tasks.

For every Task `TXXX`, expected paths are:

- `evidence/test-reports/TXXX.xml` final green JUnit
- `evidence/diffs/TXXX.patch`
- `evidence/tdd/TXXX-red.log`
- `evidence/tdd/TXXX-green.log`
- `evidence/tdd/TXXX.md`
- `evidence/reviews/TXXX-spec-review.md`
- `evidence/reviews/TXXX-code-review.md`
- `evidence/logs/TXXX/`

## TDD Evidence Rules

- A real red test must include command, date, exit code, and failure summary.
- Red output belongs in `evidence/tdd/TXXX-red.log`.
- Green output belongs in `evidence/tdd/TXXX-green.log`.
- `evidence/test-reports/TXXX.xml` is the final green JUnit report only.
- If the test is already green because bootstrap implementation exists, mark it
  `PRE_EXISTING_GREEN`.
- If red is reproduced from a clean pre-implementation baseline, mark it `REPRODUCED_RED`.
- Do not fabricate red evidence.
- Record ordinary-permission versus elevated-permission runs explicitly.

## Traceability Status Rules

`docs/TRACEABILITY_MATRIX.md` status values are frozen to:

- `planned`
- `implemented`
- `verified`
- `blocked`
- `deferred-p1`

Rows with `planned` may point to future test and evidence paths. Rows with `verified` must point to
test and evidence files that already exist. The T115 release gate must run traceability checking in
release-gate mode so every P0 requirement is `verified` and backed by existing files.

## Review Evidence Rules

- Spec Review checks requirement coverage and scope boundaries.
- Code Review checks defects, regression risk, maintainability, and test gaps.
- A Task cannot be marked `[x]` while either review is missing.
