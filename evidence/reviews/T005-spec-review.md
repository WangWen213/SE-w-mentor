# T005 Spec Review

Status: passed for branch implementation.

## Scope Checked

- Four-layer merge is represented by system, profile, project, and task `ConfigLayer` inputs.
- More restrictive policy values win over relaxed lower layers.
- Project and task layers cannot relax an existing `DENY_HARD`.
- Unknown config keys raise `ConfigMergeError`.
- Task config freezes an effective version and deterministic hash.
- Later config changes do not mutate an existing frozen task config.
- `LOCAL_FULL` and `CLOUD_DEMO` profiles exist.
- `CLOUD_DEMO` disables arbitrary repository paths, real LLM, shell, repository upload, and network.
- Effective config can explain value sources and blocked relax attempts.
- Config serialization contains no secret or API key fields.

## Result

T005 satisfies the requested branch scope without modifying security, contracts, models,
migrations, `.env.example`, or T007+ files.
