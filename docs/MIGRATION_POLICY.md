# SE-Mentor Migration Policy

This repository follows the PLAN v2 rule that schema ownership is centralized before
parallel domain model work begins.

## Ownership

Formal Alembic migrations are schema/migration owner only. The owner lane is `wt-schema`, and
`backend/migrations/**` is a shared/high-conflict resource.

Feature worktrees may prepare independent SQLAlchemy model files in their own domain area, but they
must not create formal Alembic revisions unless the task is explicitly assigned to `wt-schema`.
Schema changes from feature lanes enter the schema lane and are converted into formal migrations by
the schema/migration owner.

Later schema tasks cite this policy as their stable ownership contract before touching
`backend/migrations/**`.

## Revision Allocation

Revision allocation is owned by `wt-schema`. The schema/migration owner assigns both the migration
filename number and the Alembic `revision` identifier from the current head. Feature lanes do not
reserve numbers such as `0010_*.py` and do not invent parallel revision IDs.

Initial domain ranges:

| Range | Domain |
| --- | --- |
| 0001-0099 | Baseline and shared metadata |
| 0100-0199 | Project and configuration |
| 0200-0299 | Task and proposal |
| 0300-0399 | LLM and agent actions |
| 0400-0499 | Governance and approvals |
| 0500-0599 | Tools, transactions, validation, and audit |
| 0600-0699 | Knowledge and code index |

## Parallel Development Rule

Parallel feature worktrees may modify their own isolated model/domain files. They do not commit
formal migration files by default. When a model change needs schema persistence, the feature branch
hands the model intent to `wt-schema`; the schema/migration owner regenerates the migration from the
latest mainline head.

## Merge Rule

Before a schema/migration branch merges, the owner must:

1. Rebase onto latest `main`.
2. Check the latest migration head.
3. Rebase/regenerate the revision when the head changed.
4. Run Alembic upgrade against a temp DB.
5. Run Alembic downgrade.
6. Run Alembic upgrade again.
7. Confirm exactly one Alembic head.

## Conflict Rule

When migration files or revision graphs conflict, do not hand-splice the revision graph casually.
Return to the schema/migration owner flow, regenerate from latest main when needed, and preserve a
single clear lineage.

## CI Gate

CI and local canonical validation run `scripts/check_alembic_heads.py`. The gate semantics are:

- `0` heads -> fail closed.
- `1` head -> pass.
- More than `1` head -> fail closed.

The gate reports the detected head count, revision IDs, and failure reason so later reviewers do
not depend on manual inspection of `alembic heads`.
