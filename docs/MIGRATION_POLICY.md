# SE-Mentor Migration Policy

This repository follows the PLAN v2 rule that schema ownership is centralized before
parallel domain model work begins.

- Formal Alembic revisions are owned by the schema worktree.
- Feature worktrees may prepare independent SQLAlchemy model files, but must not create
  competing migration heads.
- Before merge, schema changes must be regenerated or rebased onto the current single head.
- CI must fail when Alembic reports more than one head.

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
