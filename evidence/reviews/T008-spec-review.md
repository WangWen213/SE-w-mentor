# T008 Spec Review

Status: PASS.

Scope reviewed:

- `docs/MIGRATION_POLICY.md`
- `scripts/check_alembic_heads.py`
- `scripts/check_all.py`
- `tests/meta/test_migration_policy.py`

Findings:

- Ownership is explicit: formal Alembic migrations are schema/migration owner only, owned by
  `wt-schema`.
- Migration files are documented as shared/high-conflict resources.
- Revision allocation is centralized so parallel branches do not reserve competing numbers or
  create multiple heads.
- Merge rules require rebase/regenerate, upgrade, downgrade, upgrade, and exactly one head.
- CI/local canonical validation runs the single-head gate and fails closed on 0 or multiple heads.
- T009 domain model files were not touched.
