# Evidence Format

T001 freezes the evidence layout used by P0 tasks.

For every Task `TXXX`, expected paths are:

- `evidence/test-reports/TXXX.xml`
- `evidence/diffs/TXXX.patch`
- `evidence/tdd/TXXX.md`
- `evidence/reviews/TXXX-spec-review.md`
- `evidence/reviews/TXXX-code-review.md`
- `evidence/logs/TXXX/`

## TDD Evidence Rules

- A real red test must include command, date, exit code, and failure summary.
- If the test is already green because bootstrap implementation exists, mark it
  `PRE_EXISTING_GREEN`.
- Do not fabricate red evidence.
- Record ordinary-permission versus elevated-permission runs explicitly.

## Review Evidence Rules

- Spec Review checks requirement coverage and scope boundaries.
- Code Review checks defects, regression risk, maintainability, and test gaps.
- A Task cannot be marked `[x]` while either review is missing.
