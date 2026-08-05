# P0 Decisions

Status: frozen for bootstrap compliance unless a later documented review changes them.

## Bootstrap Exception

T002, T003, T007, and T008 received scaffold implementation before strict red-green TDD evidence.
This is a one-time bootstrap exception. The exception does not permit fabricating red evidence:
existing tests that are already green must be marked `PRE_EXISTING_GREEN`, and any true failures
must be captured as red evidence.

## Naming

| Item | Decision |
| --- | --- |
| Product | `SE-Mentor` |
| Python package | `se_mentor` |
| Repository, CLI, Docker service | `se-mentor` |
| Deprecated spelling | `sementor` |

The existing `backend/src/se_mentor/` package path is correct and must not be renamed.

## OpenAI Provider

- API shape: Responses API.
- Default model: `gpt-5.6-terra`.
- High-complexity model: `gpt-5.6-sol`.
- Fast low-cost model: `gpt-5.6-luna`.
- Model names belong only in configuration and Provider code.
- Unit tests must use Mock Provider.
- Domain enums, migrations, and the core Agent loop must not hard-code provider model names.

## P0 Operating Rules

- T009 and later feature development is paused until T000-T008 satisfy strict DoD.
- PLAN records strict DoD state only; environment readiness is recorded in `PREP_STATUS.md`.
- No Task is marked `[x]` without red evidence, green implementation evidence, regression
  evidence, Spec Review, Code Review, evidence files, commit, and clean status.
- Existing scaffold must not be deleted, reverted, or rebuilt during compliance backfill.
- Frontend test evidence must not rely on long-term administrator or elevated execution.
