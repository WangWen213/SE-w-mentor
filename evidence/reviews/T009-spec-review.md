# T009 Spec Review

Status: PASS.

## Project

- Exists: yes, `Project`.
- Root path canonicalized: yes, `normalize_project_root_path`.
- Canonical path unique: yes, `uq_projects_normalized_root_path`.
- Unneeded fields: none beyond `id`, `root_path`, `normalized_root_path`, and timestamps.

## ProjectConfig

- Belongs to Project: yes, `project_id` FK with `ON DELETE CASCADE`.
- Preserves version: yes, integer `version`.
- Preserves effective scope: yes, `effective_scope`.
- Allows history: yes, multiple versions per project are allowed.
- Does not duplicate T005 resolver: yes, stores `config_json` only and does not resolve runtime
  `EffectiveConfig`.

## CredentialProfile

- Stores only provider, keyring reference, and configuration status.
- No credential plaintext column/path exists.
- Tests inspect SQLAlchemy columns, migration text, and SQLite dump for forbidden plaintext sinks.

## Migration

- Single Alembic head: yes, `0010_project_domain`.
- Upgrade: PASS.
- Downgrade: PASS.
- Re-upgrade: PASS.

## Scope

T010 was not started. No `task.py`, `0020_task_domain.py`, `ChangeTask`, `ChangeProposal`, or
`TaskIteration` was created.
