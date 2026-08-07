# T011 Spec Review

Status: PASS.

## Requirement Source

- Plan: `SE-Mentor_PLAN_v2_NO_REVIEW_CLOSURE.md`, T011 LLM/action domain data model.
- Spec: `SPEC.问题陈述.md`, sections 6.7 and 6.15.
- Migration policy: `docs/MIGRATION_POLICY.md`.
- User instruction: start and complete only T011, do not start T012+.

## LLMCall

- Provider/model persisted: yes, `provider_name` and `model_name`.
- Token observability: yes, required `input_tokens` and `output_tokens`; `total_tokens` is derived
  rather than separately persisted.
- Latency: yes, `latency_ms`, nullable but constrained non-negative.
- Error metadata: yes, bounded `error_code`; no raw exception/request/response dump.
- Parse status: yes, `VALID`/`INVALID` DB-constrained parse status.
- Prompt/response boundary: yes, only bounded `request_summary` and `response_summary` exist.
- Secret boundary: yes, no credential sink columns and constructor/attribute rejection for unsafe
  field names.

## AgentAction

- Bound to iteration: yes, required `iteration_id`.
- Bound to task: yes, required `task_id` per SPEC 6.7.2.
- Source LLM call: yes, optional `llm_call_id` per SPEC 6.7.2.
- Action type: reuses current frozen `contracts.enums.ActionType`.
- Parameter storage: bounded `parameters_summary` plus optional `parameters_artifact_ref`, not raw
  unbounded arguments.
- Status: DB-constrained SPEC action status values.
- Sequence: positive `action_sequence` with unique `(iteration_id, action_sequence)`.

## Contract Note

SPEC 6.7.2 lists a broader action type set than the current T004-frozen `ActionType` contract and
frontend mirror. T011 reused the frozen repository enum and did not expand contracts, snapshots, or
frontend enum mirrors in this schema task.

## Migration

- Revision: `0030_llm_action`.
- Down revision: `0020_task_domain`.
- Upgrade: PASS.
- Downgrade: PASS.
- Re-upgrade: PASS.
- Single head: PASS.

## Scope

T012 NOT STARTED.
